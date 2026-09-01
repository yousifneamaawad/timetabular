# solver.py
"""
Production-grade university scheduling engine using OR-Tools CP-SAT.

Architecture:
    1. Validate input data
    2. Create ALL decision variables once (LectureDecision owns everything)
    3. Build constraints (pure wiring — constraints.py creates zero variables)
    4. Build objective (creates auxiliary penalty variables only)
    5. Solve
    6. Save

Variable creation policy:
    - Decision variables (start, end, interval, day, period, teacher, room,
      presence literals, optional intervals, availability literals):
      created ONCE in create_variables().
    - Auxiliary penalty variables (gap, penalty, diff): created in
      build_objective() — these are not decision variables, they are
      derived terms for the objective function only.
"""

import os
import time
import threading
from typing import Optional, Callable
from dataclasses import dataclass, field
from collections import defaultdict

from ortools.sat.python import cp_model

from models import (
    Course, Teacher, Room, Student, TeacherAssignment,
    Enrollment, Availability, SolverConfig, SolverWeights
)
from database import db_manager


# ---------------------------------------------------------------------------
# Availability Decision
# ---------------------------------------------------------------------------

@dataclass
class AvailabilityLiteral:
    """Pre-built (before, after) Boolean pair for one availability block."""
    entity_type: str       # 'student', 'teacher', 'room'
    entity_id: int
    availability_index: int
    before: cp_model.IntVar
    after: cp_model.IntVar


# ---------------------------------------------------------------------------
# Lecture Decision
# ---------------------------------------------------------------------------

@dataclass
class LectureDecision:
    """
    Complete decision variable set for one lecture instance.
    
    All CP-SAT decision variables are created once and stored here.
    Constraints only read these; objectives read these and may create
    auxiliary penalty variables.
    """
    course: Course
    lecture_number: int
    
    # Core placement
    start: cp_model.IntVar
    end: cp_model.IntVar
    interval: cp_model.IntervalVar
    day: cp_model.IntVar
    period: cp_model.IntVar
    
    # Resource assignment
    teacher: cp_model.IntVar
    room: cp_model.IntVar
    
    # Teacher: presence literal + optional interval per compatible teacher
    teacher_presence: dict[int, cp_model.IntVar] = field(default_factory=dict)
    teacher_opt_intervals: dict[int, cp_model.IntervalVar] = field(default_factory=dict)
    
    # Room: presence literal + optional interval per compatible room
    room_presence: dict[int, cp_model.IntVar] = field(default_factory=dict)
    room_opt_intervals: dict[int, cp_model.IntervalVar] = field(default_factory=dict)
    
    # Availability: list of pre-built (before, after) literal pairs
    availability_literals: list[AvailabilityLiteral] = field(default_factory=list)
    
    # Pre-computed compatibility
    compatible_teacher_ids: list[int] = field(default_factory=list)
    compatible_room_ids: list[int] = field(default_factory=list)
    
    @property
    def key(self) -> tuple[int, int]:
        return (self.course.id, self.lecture_number)
    
    @property
    def duration(self) -> int:
        return self.course.duration


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class ScheduleValidator:
    """Validates input data before model construction."""
    
    def __init__(self, solver: 'SchedulerSolver'):
        self.solver = solver
        self.errors: list[str] = []
        self.warnings: list[str] = []
    
    def validate(self) -> None:
        """Run all validation checks. Raises ValueError on fatal errors."""
        self._validate_config()
        self._validate_courses()
        self._validate_rooms()
        self._validate_teachers()
        self._validate_enrollments()
        self._validate_availability()
        self._validate_feasibility()
        
        if self.errors:
            raise ValueError(
                "Schedule validation failed:\n  " + "\n  ".join(self.errors)
            )
    
    def _validate_config(self) -> None:
        cfg = self.solver.config
        if cfg.slots_per_day < 1:
            self.errors.append("slots_per_day must be >= 1")
        if cfg.days_per_week < 1:
            self.errors.append("days_per_week must be >= 1")
        if cfg.time_limit_seconds < 1:
            self.errors.append("time_limit_seconds must be >= 1")
    
    def _validate_courses(self) -> None:
        seen_ids = set()
        for c in self.solver.courses:
            if c.id in seen_ids:
                self.errors.append(f"Duplicate course ID: {c.id}")
            seen_ids.add(c.id)
            
            if c.lectures_per_week < 1:
                self.errors.append(
                    f"Course {c.id} ({c.title}): lectures_per_week must be >= 1"
                )
            if c.duration < 1:
                self.errors.append(
                    f"Course {c.id} ({c.title}): duration must be >= 1"
                )
            if c.duration > self.solver.config.slots_per_day:
                self.errors.append(
                    f"Course {c.id} ({c.title}): duration ({c.duration}) "
                    f"exceeds slots_per_day ({self.solver.config.slots_per_day})"
                )
            if c.students_per_lecture < 1:
                self.errors.append(
                    f"Course {c.id} ({c.title}): students_per_lecture must be >= 1"
                )
            
            # Check compatible rooms exist
            compatible = [
                r for r in self.solver.rooms
                if r.capacity >= c.students_per_lecture
                and (not c.requires_lab or r.is_lab)
            ]
            if not compatible:
                self.errors.append(
                    f"Course {c.id} ({c.title}): no compatible room "
                    f"(needs capacity >= {c.students_per_lecture}"
                    f"{', requires lab' if c.requires_lab else ''})"
                )
            
            # Check at least one teacher assigned
            course_teachers = [
                ta.teacher_id for ta in self.solver.teacher_assignments
                if ta.course_id == c.id
            ]
            if not course_teachers:
                self.errors.append(
                    f"Course {c.id} ({c.title}): no teacher assigned"
                )
    
    def _validate_rooms(self) -> None:
        seen_ids = set()
        for r in self.solver.rooms:
            if r.id in seen_ids:
                self.errors.append(f"Duplicate room ID: {r.id}")
            seen_ids.add(r.id)
            if r.capacity < 1:
                self.errors.append(f"Room {r.id} ({r.name}): capacity must be >= 1")
    
    def _validate_teachers(self) -> None:
        seen_ids = set()
        for t in self.solver.teachers:
            if t.id in seen_ids:
                self.errors.append(f"Duplicate teacher ID: {t.id}")
            seen_ids.add(t.id)
    
    def _validate_enrollments(self) -> None:
        seen_pairs = set()
        for e in self.solver.enrollments:
            pair = (e.student_id, e.course_id)
            if pair in seen_pairs:
                self.warnings.append(
                    f"Duplicate enrollment: student {e.student_id}, "
                    f"course {e.course_id}"
                )
            seen_pairs.add(pair)
            
            if e.student_id not in self.solver.student_by_id:
                self.warnings.append(
                    f"Enrollment: student {e.student_id} does not exist — skipping"
                )
            if e.course_id not in self.solver.course_by_id:
                self.warnings.append(
                    f"Enrollment: course {e.course_id} does not exist — skipping"
                )
    
    def _validate_availability(self) -> None:
        print("=" * 60)
        print("CONFIG")
        print("slots_per_day =", self.solver.config.slots_per_day)
        print("days_per_week =", self.solver.config.days_per_week)
        print("=" * 60)
        for label, avail_list, entity_map in [
            ("student", self.solver.student_availability, self.solver.student_by_id),
            ("teacher", self.solver.teacher_availability, self.solver.teacher_by_id),
            ("room", self.solver.room_availability, self.solver.room_by_id),
        ]:
            for i, a in enumerate(avail_list):
                if a.entity_id not in entity_map:
                    self.warnings.append(
                        f"{label}_availability[{i}]: entity {a.entity_id} "
                        f"does not exist — skipping"
                    )
                if a.day < 1 or a.day > self.solver.config.days_per_week:
                    self.errors.append(
                        f"{label}_availability[{i}]: day {a.day} out of range"
                    )
                if a.start_period < 1 or a.start_period > self.solver.config.slots_per_day:
                    self.errors.append(
                        f"{label}_availability[{i}]: start_period out of range"
                    )
                if a.end_period < 1 or a.end_period > self.solver.config.slots_per_day:
                    self.errors.append(
                        f"{label}_availability[{i}]: end_period out of range"
                    )
                if a.start_period > a.end_period:
                    self.errors.append(
                        f"{label}_availability[{i}]: start_period > end_period"
                    )
    
    def _validate_feasibility(self) -> None:
        """
        Detect obviously impossible schedules before building the model.
        
        Checks:
        - Total lecture slots don't exceed available timetable slots
        - Teacher workload doesn't exceed available slots
        - Room capacity doesn't create impossible student placements
        """
        spd = self.solver.config.slots_per_day
        dpw = self.solver.config.days_per_week
        total_slots = spd * dpw
        
        # Total lecture-period demand
        total_demand = sum(
            c.lectures_per_week * c.duration
            for c in self.solver.courses
        )
        
        # Each room can host one lecture per slot
        room_capacity_slots = total_slots * len(self.solver.rooms)
        if total_demand > room_capacity_slots:
            self.errors.append(
                f"Total lecture demand ({total_demand} slot-periods) exceeds "
                f"room capacity ({room_capacity_slots} slot-periods across "
                f"{len(self.solver.rooms)} rooms)"
            )
        
        # Per-teacher workload check
        for tid, course_ids in self.solver.teacher_courses.items():
            teacher_demand = sum(
                self.solver.course_by_id[cid].lectures_per_week *
                self.solver.course_by_id[cid].duration
                for cid in course_ids
                if cid in self.solver.course_by_id
            )
            if teacher_demand > total_slots:
                teacher = self.solver.teacher_by_id.get(tid)
                name = teacher.name if teacher else f"ID {tid}"
                self.errors.append(
                    f"Teacher {name}: demand ({teacher_demand} slot-periods) "
                    f"exceeds available slots ({total_slots})"
                )


# ---------------------------------------------------------------------------
# Solution Monitoring
# ---------------------------------------------------------------------------

class SolutionCallback(cp_model.CpSolverSolutionCallback):
    """Tracks solver progress and retains only the best solution."""
    
    def __init__(self, lectures: list[LectureDecision]):
        super().__init__()
        self._lectures = lectures
        self.solution_count: int = 0
        self.best_objective: float = float('inf')
        self.solve_start_time: float = time.time()
        self.best_solution_data: Optional[dict] = None
        
    def on_solution_callback(self) -> None:
        self.solution_count += 1
        current_obj = self.ObjectiveValue()
        
        if current_obj < self.best_objective:
            self.best_objective = current_obj
            self.best_solution_data = self._extract_solution()
    
    def _extract_solution(self) -> dict:
        solution = {}
        for lec in self._lectures:
            solution[lec.key] = {
                'start': self.Value(lec.start),
                'end': self.Value(lec.end),
                'teacher': self.Value(lec.teacher),
                'room': self.Value(lec.room),
                'day': self.Value(lec.day),
                'period': self.Value(lec.period),
            }
        return solution
    
    @property
    def elapsed_time(self) -> float:
        return time.time() - self.solve_start_time


class SearchInterrupter:
    """Background thread that interrupts the solver on cancellation."""
    
    def __init__(self, solver: cp_model.CpSolver, check_cancel: Callable[[], bool]):
        self._solver = solver
        self._check_cancel = check_cancel
        
    def poll(self) -> None:
        while True:
            if self._check_cancel():
                self._solver.InterruptSearch()
                break
            time.sleep(0.1)


# ---------------------------------------------------------------------------
# Core Solver
# ---------------------------------------------------------------------------

class SchedulerSolver:
    """
    Production university timetabling engine.
    
    All decision variables are created in create_variables().
    Constraints are pure wiring (see constraints.py).
    Objectives create auxiliary penalty variables as needed.
    """
    
    def __init__(self,config: SolverConfig,weights: Optional[SolverWeights] = None):
        self.config = config 
        self.weights = weights or SolverWeights()
        self.model = cp_model.CpModel()
        
        # Raw data (as stored: "available window" rows — see
        # apply_availability_semantics() for the derived form)
        self.courses: list[Course] = []
        self.teachers: list[Teacher] = []
        self.rooms: list[Room] = []
        self.students: list[Student] = []
        self.enrollments: list[Enrollment] = []
        self.teacher_assignments: list[TeacherAssignment] = []
        self.student_availability: list[Availability] = []
        self.teacher_availability: list[Availability] = []
        self.room_availability: list[Availability] = []
        
        # Derived data: "unavailable gap" rows computed from the raw
        # *_availability lists above by apply_availability_semantics().
        # This is what the constraint-building code actually consumes.
        # Kept separate (never overwrites the raw lists) so re-deriving
        # is always safe/idempotent and validate() always sees real input.
        self.student_unavailable_blocks: list[Availability] = []
        self.teacher_unavailable_blocks: list[Availability] = []
        self.room_unavailable_blocks: list[Availability] = []
        
        # Decision variables
        self.lectures: list[LectureDecision] = []
        
        # Lookups
        self.course_by_id: dict[int, Course] = {}
        self.teacher_by_id: dict[int, Teacher] = {}
        self.room_by_id: dict[int, Room] = {}
        self.student_by_id: dict[int, Student] = {}
        self.student_courses: dict[int, list[int]] = defaultdict(list)
        self.teacher_courses: dict[int, list[int]] = defaultdict(list)
        self.course_teachers: dict[int, list[int]] = defaultdict(list)
        self.teacher_preferred_room: dict[tuple[int, int], Optional[int]] = {}
        
        # Pre-indexed availability (built during create_variables)
        self._room_availability_by_room: dict[int, list[tuple[int, Availability]]] = (
            defaultdict(list)
        )
        
        # Objective terms
        self.objective_terms: list = []
        # Soft student-availability violation indicators, penalized in
        # build_objective() rather than forbidden outright. See
        # constraints.py's _add_availability_constraints for why.
        self.student_availability_violations: list = []
        
        # State
        self.callback: Optional[SolutionCallback] = None
    
    # -----------------------------------------------------------------------
    # Data Loading
    # -----------------------------------------------------------------------
    def load_database(self) -> None:
        """Load all data from the database and build lookups."""

        # Load configuration using the database manager
        self.config = db_manager.load_solver_config()

        with db_manager.get_connection() as conn:
            self._load_entities(conn)
            self._load_relationships(conn)
            self._load_availability(conn)

        self._build_lookups()
    def _load_entities(self, conn) -> None:
        self.courses = [Course(**dict(r)) for r in conn.execute("SELECT * FROM courses").fetchall()]
        self.teachers = [Teacher(**dict(r)) for r in conn.execute("SELECT * FROM teachers").fetchall()]
        self.rooms = [Room(**dict(r)) for r in conn.execute("SELECT * FROM rooms").fetchall()]
        self.students = [Student(**dict(r)) for r in conn.execute("SELECT * FROM students").fetchall()]
    
    def _load_relationships(self, conn) -> None:
        self.enrollments = [Enrollment(**dict(r)) for r in conn.execute("SELECT * FROM enrollment").fetchall()]
        self.teacher_assignments = [
            TeacherAssignment(**dict(r))
            for r in conn.execute("SELECT * FROM teacher_assignments").fetchall()
        ]
    
    def _load_availability(self, conn) -> None:
        """
        Load raw availability rows as stored — "available window" form
        (see generate_mock_data.py's docstring: "All records represent
        periods when the entity IS AVAILABLE"). validate() runs against
        this raw form. The conversion into "unavailable gap" form (what
        the constraint-building code actually needs) happens later, in
        apply_availability_semantics(), right before create_variables()
        consumes it — so validation always reflects the real input data,
        not a derived representation.
        """
        self.student_availability = [
            Availability(**dict(r))
            for r in conn.execute("SELECT * FROM student_availability").fetchall()
        ]
        self.teacher_availability = [
            Availability(**dict(r))
            for r in conn.execute("SELECT * FROM teacher_availability").fetchall()
        ]
        self.room_availability = [
            Availability(**dict(r))
            for r in conn.execute("SELECT * FROM room_availability").fetchall()
        ]

    def apply_availability_semantics(self) -> None:
        """
        Derive "unavailable gap" blocks from the loaded "available window"
        rows. Must be called after validate() and before create_variables()
        uses the *_unavailable_blocks fields. Safe to call more than once:
        it always re-derives from the untouched raw *_availability lists,
        it never mutates them.
        """
        spd = self.config.slots_per_day
        dpw = self.config.days_per_week
        self.student_unavailable_blocks = self._invert_availability(self.student_availability, spd, dpw)
        self.teacher_unavailable_blocks = self._invert_availability(self.teacher_availability, spd, dpw)
        self.room_unavailable_blocks = self._invert_availability(self.room_availability, spd, dpw)

    @staticmethod
    def _invert_availability(
        rows: list[Availability], spd: int, dpw: int
    ) -> list[Availability]:
        """
        Convert "available window" rows into "unavailable gap" rows.

        Two deliberate design decisions, both worth re-confirming once
        real (non-mock) data entry exists:

        1. An entity with ZERO rows anywhere in the table is left with
           NO gaps at all, i.e. treated as available all week. This
           matches "no data entered = no preference stated."

        2. An entity that HAS rows on some days but none on a specific
           day is treated as fully UNAVAILABLE that day, not fully
           available. This matches how generate_mock_data.py's patterns
           work (e.g. a day mapping to `[]` means "not available this
           day"), but if a future data-entry UI lets someone save a
           partial week and simply never gets around to a given day,
           this default would wrongly block that day. Revisit if so.

        Given those two rules, for every entity that has >=1 row, and
        for every day 1..dpw:
          - if the entity has no recorded available window that day,
            the whole day is a gap (see decision 2 above)
          - otherwise the gaps are whatever periods aren't covered by
            the (merged) union of that entity's available windows
        """
        by_entity_day: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
        entities: set[int] = set()
        for row in rows:
            by_entity_day[(row.entity_id, int(row.day))].append(
                (row.start_period, row.end_period)
            )
            entities.add(row.entity_id)

        gaps: list[Availability] = []
        next_id = 1
        for entity_id in entities:
            for day in range(1, dpw + 1):
                windows = sorted(by_entity_day.get((entity_id, day), []))

                if not windows:
                    gaps.append(Availability(next_id, entity_id, day, 1, spd))
                    next_id += 1
                    continue

                # Merge overlapping/adjacent available windows.
                merged: list[tuple[int, int]] = []
                for s, e in windows:
                    if merged and s <= merged[-1][1] + 1:
                        merged[-1] = (merged[-1][0], max(merged[-1][1], e))
                    else:
                        merged.append((s, e))

                # Gaps = whatever isn't covered by the merged windows.
                cursor = 1
                for s, e in merged:
                    if s > cursor:
                        gaps.append(Availability(next_id, entity_id, day, cursor, s - 1))
                        next_id += 1
                    cursor = max(cursor, e + 1)
                if cursor <= spd:
                    gaps.append(Availability(next_id, entity_id, day, cursor, spd))
                    next_id += 1

        return gaps
    
    def _build_lookups(self) -> None:
        self.course_by_id = {c.id: c for c in self.courses}
        self.teacher_by_id = {t.id: t for t in self.teachers}
        self.room_by_id = {r.id: r for r in self.rooms}
        self.student_by_id = {s.id: s for s in self.students}
        
        for e in self.enrollments:
            if e.student_id in self.student_by_id and e.course_id in self.course_by_id:
                self.student_courses[e.student_id].append(e.course_id)
        
        for ta in self.teacher_assignments:
            self.teacher_courses[ta.teacher_id].append(ta.course_id)
            self.course_teachers[ta.course_id].append(ta.teacher_id)
            self.teacher_preferred_room[(ta.teacher_id, ta.course_id)] = ta.preferred_room_id
    
    # -----------------------------------------------------------------------
    # Validation
    # -----------------------------------------------------------------------
    
    def validate(self) -> None:
        """Validate input data. Raises ValueError on fatal problems."""
        ScheduleValidator(self).validate()
    
    # -----------------------------------------------------------------------
    # Variable Creation
    # -----------------------------------------------------------------------
    
    def create_variables(self) -> None:
        """
        Create ALL decision variables for every lecture.
        
        For each lecture instance, creates:
            - Core placement: start, end, interval, day, period
            - Day-boundary constraint: period + duration <= slots_per_day
            - Resource assignment: teacher, room
            - Teacher/room presence literals with AddExactlyOne
            - Teacher/room optional intervals
            - Availability (before, after) literals (only for relevant blocks)
        
        Also adds symmetry-breaking: lectures of the same course are
        ordered by start time.
        """
        spd = self.config.slots_per_day
        dpw = self.config.days_per_week
        horizon = dpw * spd
        
        # Convert loaded "available window" rows into "unavailable gap"
        # rows now that validation (which needs the raw form) is done.
        self.apply_availability_semantics()
        
        # Pre-index availability for efficient lookup
        self._index_availability()
        
        # Pre-compute student/teacher availability by course
        student_avail_by_course = self._index_student_availability()
        teacher_avail_by_course = self._index_teacher_availability()
        
        for course in self.courses:
            course_lectures = []
            for lec_num in range(course.lectures_per_week):
                lec = self._create_single_lecture(
                    course, lec_num, spd, dpw, horizon,
                    student_avail_by_course,
                    teacher_avail_by_course
                )
                self.lectures.append(lec)
                course_lectures.append(lec)
            
            # Symmetry breaking: order lectures of the same course
            for i in range(len(course_lectures) - 1):
                self.model.Add(
                    course_lectures[i].start < course_lectures[i + 1].start
                )
    
    def _index_availability(self) -> None:
        """Pre-index room unavailable blocks by room ID for efficient lookup."""
        self._room_availability_by_room.clear()
        for i, avail in enumerate(self.room_unavailable_blocks):
            self._room_availability_by_room[avail.entity_id].append((i, avail))
    
    def _index_student_availability(self) -> dict[int, list[tuple[int, Availability]]]:
        """Index student unavailable blocks by course ID."""
        result: dict[int, list[tuple[int, Availability]]] = defaultdict(list)
        for i, avail in enumerate(self.student_unavailable_blocks):
            student_courses = self.student_courses.get(avail.entity_id, [])
            for cid in student_courses:
                result[cid].append((i, avail))
        return result
    
    def _index_teacher_availability(self) -> dict[int, list[tuple[int, Availability]]]:
        """Index teacher unavailable blocks by course ID."""
        result: dict[int, list[tuple[int, Availability]]] = defaultdict(list)
        for i, avail in enumerate(self.teacher_unavailable_blocks):
            teacher_courses = self.teacher_courses.get(avail.entity_id, [])
            for cid in teacher_courses:
                result[cid].append((i, avail))
        return result
    
    def _create_single_lecture(
        self,
        course: Course,
        lec_num: int,
        spd: int,
        dpw: int,
        horizon: int,
        student_avail_by_course: dict[int, list[tuple[int, Availability]]],
        teacher_avail_by_course: dict[int, list[tuple[int, Availability]]]
    ) -> LectureDecision:
        """Create all decision variables for one lecture instance."""
        cid = course.id
        ln = lec_num
        dur = course.duration
        
        # --- Core placement ---
        start = self.model.NewIntVar(0, horizon - dur, f"s_{cid}_{ln}")
        end = self.model.NewIntVar(dur, horizon, f"e_{cid}_{ln}")
        self.model.Add(end == start + dur)
        interval = self.model.NewIntervalVar(start, dur, end, f"iv_{cid}_{ln}")
        
        day_zero = self.model.NewIntVar(0, dpw - 1, f"dz_{cid}_{ln}")
        self.model.AddDivisionEquality(day_zero, start, spd)
        day = self.model.NewIntVar(1, dpw, f"d_{cid}_{ln}")
        self.model.Add(day == day_zero + 1)
        
        # FIX 1: Period domain must be 0..spd-1 (not 0..spd-duration)
        # because AddModuloEquality can produce any value in that range.
        period = self.model.NewIntVar(0, spd - 1, f"p_{cid}_{ln}")
        self.model.AddModuloEquality(period, start, spd)
        
        # FIX 2: Prevent lectures from crossing day boundaries.
        # period + duration <= slots_per_day ensures the lecture
        # fits entirely within one day.
        self.model.Add(period + dur <= spd)
        
        # --- Resource variables ---
        compatible_teachers = self.course_teachers.get(cid, [])
        compatible_rooms = self._get_compatible_room_ids(course)
        
        teacher = self._create_domain_var(compatible_teachers, f"t_{cid}_{ln}")
        room = self._create_domain_var(compatible_rooms, f"r_{cid}_{ln}")
        
        lec = LectureDecision(
            course=course,
            lecture_number=ln,
            start=start, end=end, interval=interval,
            day=day, period=period,
            teacher=teacher, room=room,
            compatible_teacher_ids=compatible_teachers,
            compatible_room_ids=compatible_rooms,
        )
        
        # --- Teacher presence + optional intervals ---
        teacher_presences = []
        for tid in compatible_teachers:
            presence = self.model.NewBoolVar(f"tp_{cid}_{ln}_{tid}")
            self.model.Add(teacher == tid).OnlyEnforceIf(presence)
            self.model.Add(teacher != tid).OnlyEnforceIf(presence.Not())
            teacher_presences.append(presence)
            
            opt_iv = self.model.NewOptionalIntervalVar(
                start, dur, end, presence, f"toi_{cid}_{ln}_{tid}"
            )
            lec.teacher_presence[tid] = presence
            lec.teacher_opt_intervals[tid] = opt_iv
        
        if teacher_presences:
            self.model.AddExactlyOne(teacher_presences)
        
        # --- Room presence + optional intervals ---
        room_presences = []
        for rid in compatible_rooms:
            presence = self.model.NewBoolVar(f"rp_{cid}_{ln}_{rid}")
            self.model.Add(room == rid).OnlyEnforceIf(presence)
            self.model.Add(room != rid).OnlyEnforceIf(presence.Not())
            room_presences.append(presence)
            
            opt_iv = self.model.NewOptionalIntervalVar(
                start, dur, end, presence, f"roi_{cid}_{ln}_{rid}"
            )
            lec.room_presence[rid] = presence
            lec.room_opt_intervals[rid] = opt_iv
        
        if room_presences:
            self.model.AddExactlyOne(room_presences)
        
        # --- Availability literals (only for relevant blocks) ---
        self._create_availability_literals(
            lec, spd,
            student_avail_by_course.get(cid, []),
            teacher_avail_by_course.get(cid, []),
            compatible_rooms
        )
        
        return lec
    
    def _create_domain_var(self, values: list[int], name: str) -> cp_model.IntVar:
        """Create an IntVar restricted to the given domain values."""
        if values:
            return self.model.NewIntVarFromDomain(
                cp_model.Domain.FromValues(values), name
            )
        return self.model.NewIntVar(0, 0, name)
    
    def _get_compatible_room_ids(self, course: Course) -> list[int]:
        return [
            r.id for r in self.rooms
            if r.capacity >= course.students_per_lecture
            and (not course.requires_lab or r.is_lab)
        ]
    
    def _create_availability_literals(
        self,
        lec: LectureDecision,
        spd: int,
        student_avails: list[tuple[int, Availability]],
        teacher_avails: list[tuple[int, Availability]],
        compatible_rooms: list[int]
    ) -> None:
        """
        Pre-create (before, after) literals for every availability block
        that could affect this lecture.
        
        Uses pre-indexed room availability for O(compatible_rooms) lookup
        instead of O(all_rooms) scan.
        """
        cid = lec.course.id
        ln = lec.lecture_number
        
        # Student availability
        for idx, avail in student_avails:
            self._add_avail_pair(
                lec, avail, spd, cid, ln,
                entity_type='student', entity_id=avail.entity_id, idx=idx
            )
        
        # Teacher availability
        for idx, avail in teacher_avails:
            self._add_avail_pair(
                lec, avail, spd, cid, ln,
                entity_type='teacher', entity_id=avail.entity_id, idx=idx
            )
        
        # FIX 5: Room availability — use pre-indexed lookup
        # Only check rooms that are compatible with this lecture
        for rid in compatible_rooms:
            for idx, avail in self._room_availability_by_room.get(rid, []):
                self._add_avail_pair(
                    lec, avail, spd, cid, ln,
                    entity_type='room', entity_id=rid, idx=idx
                )
    
    def _add_avail_pair(
        self, lec: LectureDecision, avail: Availability, spd: int,
        cid: int, ln: int,
        entity_type: str, entity_id: int, idx: int
    ) -> None:
        """Create a (before, after) BoolVar pair for one availability block."""
        day_start = (avail.day - 1) * spd
        unavail_start = day_start + avail.start_period - 1
        unavail_end = day_start + avail.end_period
        
        before = self.model.NewBoolVar(
            f"ab_{entity_type[0]}{entity_id}_{idx}_{cid}_{ln}"
        )
        after = self.model.NewBoolVar(
            f"aa_{entity_type[0]}{entity_id}_{idx}_{cid}_{ln}"
        )
        
        self.model.Add(lec.end <= unavail_start).OnlyEnforceIf(before)
        self.model.Add(lec.end > unavail_start).OnlyEnforceIf(before.Not())
        
        self.model.Add(lec.start >= unavail_end).OnlyEnforceIf(after)
        self.model.Add(lec.start < unavail_end).OnlyEnforceIf(after.Not())
        
        lec.availability_literals.append(
            AvailabilityLiteral(
                entity_type=entity_type,
                entity_id=entity_id,
                availability_index=idx,
                before=before,
                after=after,
            )
        )
    
    # -----------------------------------------------------------------------
    # Constraint Building
    # -----------------------------------------------------------------------
    
    def build_constraints(self) -> None:
        """Build all hard constraints. Delegates to constraints.py."""
        from constraints import build_all_constraints
        build_all_constraints(self)
    
    # -----------------------------------------------------------------------
    # Objective Building
    # -----------------------------------------------------------------------
    
    def build_objective(self) -> None:
        """Construct the multi-component objective function."""
        w = self.weights
        
        if w.student_gaps > 0:
            self._add_gap_objective('student', w.student_gaps)
        if w.teacher_gaps > 0:
            self._add_gap_objective('teacher', w.teacher_gaps)
        if w.morning_preference > 0:
            self._add_morning_preference()
        if w.evening_penalty > 0:
            self._add_evening_penalty()
        if w.preferred_room > 0:
            self._add_preferred_room_objective()
        if w.student_availability_violation > 0 and self.student_availability_violations:
            self.objective_terms.append(
                w.student_availability_violation * sum(self.student_availability_violations)
            )
        
        if self.objective_terms:
            self.model.Minimize(sum(self.objective_terms))
    
    def _add_gap_objective(self, entity_type: str, weight: int) -> None:
        """
        Minimize gaps in daily schedules.
        
        Uses span-based formulation:
          gap_on_day = max_end - min_start - total_duration_on_day
        
        This correctly measures the total idle time between lectures on a
        given day. Assumes no-overlap constraints are already enforced
        (so lectures on the same day for the same entity never overlap).
        """
        if entity_type == 'student':
            entity_courses = self.student_courses
        else:
            entity_courses = self.teacher_courses
        
        spd = self.config.slots_per_day
        horizon = self.config.days_per_week * spd
        
        for entity_id, course_ids in entity_courses.items():
            entity_lectures = [
                lec for lec in self.lectures
                if lec.course.id in course_ids
            ]
            if len(entity_lectures) < 2:
                continue
            
            for day in range(1, self.config.days_per_week + 1):
                self._add_span_gap_penalty(
                    entity_lectures, day, weight, horizon,
                    f"gap_{entity_type[0]}{entity_id}"
                )
    
    def _add_span_gap_penalty(
        self,
        lectures: list[LectureDecision],
        day: int,
        weight: int,
        horizon: int,
        prefix: str
    ) -> None:
        """
        Span-based gap penalty for one entity on one day.
        
        gap = max(0, span - total_duration)
        where:
          span = max_end - min_start (when >= 2 lectures on day)
          total_duration = sum of durations of lectures on this day
        
        Uses sentinel values so AddMinEquality/AddMaxEquality work
        correctly even when some lectures are not on this day:
          - min_start uses 'horizon' as sentinel for absent lectures
          - max_end uses '0' as sentinel for absent lectures
        """
        n = len(lectures)
        
        # On-day literals
        on_day = []
        for i, lec in enumerate(lectures):
            is_on = self.model.NewBoolVar(f"{prefix}_on_{day}_{i}")
            self.model.Add(lec.day == day).OnlyEnforceIf(is_on)
            self.model.Add(lec.day != day).OnlyEnforceIf(is_on.Not())
            on_day.append(is_on)
        
        # Count lectures on this day
        count = self.model.NewIntVar(0, n, f"{prefix}_cnt_{day}")
        self.model.Add(count == sum(on_day))
        
        has_multiple = self.model.NewBoolVar(f"{prefix}_has_{day}")
        self.model.Add(count >= 2).OnlyEnforceIf(has_multiple)
        self.model.Add(count <= 1).OnlyEnforceIf(has_multiple.Not())
        
        # Total duration of lectures on this day
        total_dur = self.model.NewIntVar(0, n * self.config.slots_per_day, f"{prefix}_dur_{day}")
        dur_terms = []
        for i, lec in enumerate(lectures):
            dc = self.model.NewIntVar(0, lec.duration, f"{prefix}_dc_{day}_{i}")
            self.model.Add(dc == lec.duration).OnlyEnforceIf(on_day[i])
            self.model.Add(dc == 0).OnlyEnforceIf(on_day[i].Not())
            dur_terms.append(dc)
        self.model.Add(total_dur == sum(dur_terms))
        
        # Min start (with sentinel)
        min_start = self.model.NewIntVar(0, horizon, f"{prefix}_mins_{day}")
        cond_starts = []
        for i, lec in enumerate(lectures):
            cs = self.model.NewIntVar(0, horizon, f"{prefix}_cs_{day}_{i}")
            self.model.Add(cs == lec.start).OnlyEnforceIf(on_day[i])
            self.model.Add(cs == horizon).OnlyEnforceIf(on_day[i].Not())
            cond_starts.append(cs)
        self.model.AddMinEquality(min_start, cond_starts)
        
        # Max end (with sentinel)
        max_end = self.model.NewIntVar(0, horizon, f"{prefix}_maxe_{day}")
        cond_ends = []
        for i, lec in enumerate(lectures):
            ce = self.model.NewIntVar(0, horizon, f"{prefix}_ce_{day}_{i}")
            self.model.Add(ce == lec.end).OnlyEnforceIf(on_day[i])
            self.model.Add(ce == 0).OnlyEnforceIf(on_day[i].Not())
            cond_ends.append(ce)
        self.model.AddMaxEquality(max_end, cond_ends)
        
        # Span
        span = self.model.NewIntVar(0, horizon, f"{prefix}_span_{day}")
        self.model.Add(span == max_end - min_start).OnlyEnforceIf(has_multiple)
        self.model.Add(span == 0).OnlyEnforceIf(has_multiple.Not())
        
        # Gap = span - total_duration (non-negative)
        gap = self.model.NewIntVar(0, horizon, f"{prefix}_gap_{day}")
        self.model.Add(gap >= span - total_dur)
        self.model.Add(gap >= 0)
        
        penalty = self.model.NewIntVar(0, weight * horizon, f"{prefix}_pen_{day}")
        self.model.Add(penalty == gap * weight)
        self.objective_terms.append(penalty)
    
    def _add_morning_preference(self) -> None:
        """Prefer earlier periods: penalty = period * weight."""
        w = self.weights.morning_preference
        for lec in self.lectures:
            penalty = self.model.NewIntVar(
                0, w * self.config.slots_per_day,
                f"mp_{lec.course.id}_{lec.lecture_number}"
            )
            self.model.Add(penalty == lec.period * w)
            self.objective_terms.append(penalty)
    
    def _add_evening_penalty(self) -> None:
        """Heavy penalty for scheduling in the last two periods."""
        eve_start = self.config.slots_per_day - 2
        w = self.weights.evening_penalty
        
        for lec in self.lectures:
            is_eve = self.model.NewBoolVar(f"ev_{lec.course.id}_{lec.lecture_number}")
            self.model.Add(lec.period >= eve_start).OnlyEnforceIf(is_eve)
            self.model.Add(lec.period < eve_start).OnlyEnforceIf(is_eve.Not())
            
            ep = self.model.NewIntVar(0, w, f"ep_{lec.course.id}_{lec.lecture_number}")
            self.model.Add(ep == w).OnlyEnforceIf(is_eve)
            self.model.Add(ep == 0).OnlyEnforceIf(is_eve.Not())
            self.objective_terms.append(ep)
    
    def _add_preferred_room_objective(self) -> None:
        """
        Penalize not using the teacher's preferred room.
        
        Only evaluates the preferred-room check when the teacher is actually
        assigned to this lecture (guarded by is_teacher presence literal).
        """
        w = self.weights.preferred_room
        
        for lec in self.lectures:
            cid = lec.course.id
            ln = lec.lecture_number
            
            for tid in lec.compatible_teacher_ids:
                preferred = self.teacher_preferred_room.get((tid, cid))
                if preferred is None:
                    continue
                
                is_teacher = lec.teacher_presence.get(tid)
                if is_teacher is None:
                    continue
                
                # uses_pref = (room == preferred) — only relevant when is_teacher
                uses_pref = self.model.NewBoolVar(f"up_{cid}_{ln}_{tid}")
                self.model.Add(lec.room == preferred).OnlyEnforceIf(uses_pref)
                self.model.Add(lec.room != preferred).OnlyEnforceIf(uses_pref.Not())
                
                # FIX 4: not_uses_pref = NOT uses_pref
                # Uses AddBoolXOr with two variables (proper usage)
                not_uses_pref = self.model.NewBoolVar(f"nup_{cid}_{ln}_{tid}")
                self.model.AddBoolXOr([uses_pref, not_uses_pref])
                
                # penalize = is_teacher AND not_uses_pref (linearized)
                penalize = self.model.NewBoolVar(f"pen_{cid}_{ln}_{tid}")
                self.model.Add(penalize <= is_teacher)
                self.model.Add(penalize <= not_uses_pref)
                self.model.Add(penalize >= is_teacher + not_uses_pref - 1)
                
                penalty = self.model.NewIntVar(0, w, f"pp_{cid}_{ln}_{tid}")
                self.model.Add(penalty == w).OnlyEnforceIf(penalize)
                self.model.Add(penalty == 0).OnlyEnforceIf(penalize.Not())
                self.objective_terms.append(penalty)
    
    # -----------------------------------------------------------------------
    # Solver Execution
    # -----------------------------------------------------------------------
    
    def solve(
        self, is_cancelled: Optional[Callable[[], bool]] = None
    ) -> tuple[bool, Optional[dict]]:
        """Run the CP-SAT solver."""
        # FIX 3: Check model validity and report errors
        validation_error = self.model.Validate()
        if validation_error:
            raise ValueError(f"CP-SAT model validation failed: {validation_error}")
        
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = self.config.time_limit_seconds
        # Use os.cpu_count() for explicit worker count (more predictable)
        solver.parameters.num_search_workers = os.cpu_count() or 8
        solver.parameters.log_search_progress = True
        solver.parameters.random_seed = getattr(self.config, 'random_seed', 42)
        
        self.callback = SolutionCallback(self.lectures)
        
        if is_cancelled:
            interrupter = SearchInterrupter(solver, is_cancelled)
            threading.Thread(target=interrupter.poll, daemon=True).start()
        
        solve_start = time.time()
        status = solver.Solve(self.model, self.callback)
        solve_time = time.time() - solve_start
        
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return True, self.callback.best_solution_data
        if self.callback.best_solution_data is not None:
            return True, self.callback.best_solution_data
        
        return False, None
    
    # -----------------------------------------------------------------------
    # Persistence
    # -----------------------------------------------------------------------
    
    def save_schedule(self, solution_data: dict) -> None:
        """Persist the solution to the database."""
        entries = []
        for key, vals in solution_data.items():
            course_id, lec_num = key
            course = self.course_by_id[course_id]
            entries.append({
                'course_id': course_id,
                'lecture_number': lec_num,
                'teacher_id': vals['teacher'],
                'room_id': vals['room'],
                'day': vals['day'],
                'start_period': vals['period'] + 1,
                'duration': course.duration,
            })
        
        with db_manager.get_connection() as conn:
            conn.execute("DELETE FROM schedule")
            conn.executemany(
                """INSERT INTO schedule 
                   (course_id, lecture_number, teacher_id, room_id,
                    day, start_period, duration)
                   VALUES (:course_id, :lecture_number, :teacher_id,
                           :room_id, :day, :start_period, :duration)""",
                entries
            )
            conn.commit()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def solve_schedule(
    config: Optional[SolverConfig] = None,
    weights: Optional[SolverWeights] = None,
    is_cancelled: Optional[Callable[[], bool]] = None
) -> tuple[bool, str]:
    """
    High-level entry point for the scheduling engine.
    
    Args:
        config: Solver configuration.
        weights: Objective weights.
        is_cancelled: Callback returning True to abort.
        
    Returns:
        Tuple of (success, message).
    """
    try:
        solver = SchedulerSolver(config, weights)
        solver.load_database()
        solver.validate()
        solver.create_variables()
        solver.build_constraints()
        solver.build_objective()
        
        success, solution = solver.solve(is_cancelled)
        
        if success and solution:
            solver.save_schedule(solution)
            return True, (
                f"Schedule optimized! "
                f"Solutions found: {solver.callback.solution_count}"
            )
        return False, "No feasible schedule found."
            
    except ValueError as e:
        return False, f"Validation error: {str(e)}"
    except Exception as e:
        return False, f"Solver error: {str(e)}"
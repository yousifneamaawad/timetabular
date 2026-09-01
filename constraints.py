# constraints.py
"""
Hard constraint builders for the scheduling engine.

ALL CP-SAT decision variables are created in solver.py's create_variables().
This module only wires pre-built variables together — it creates ZERO new
BoolVar, IntVar, or IntervalVar objects.

Constraints:
    - Teacher no-overlap: AddNoOverlap(pre-built optional intervals)
    - Room no-overlap: AddNoOverlap(pre-built optional intervals)
    - Student no-overlap: AddNoOverlap(mandatory intervals)
    - Availability: AddBoolOr(pre-built before/after literals)
    - Same-day: AddAllDifferent(pre-built day variables)
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from solver import SchedulerSolver


def build_all_constraints(solver: 'SchedulerSolver') -> None:
    """Wire all hard constraints using pre-built variables only."""
    _add_teacher_no_overlap(solver)
    _add_room_no_overlap(solver)
    _add_student_no_overlap(solver)
    _add_availability_constraints(solver)
    _add_same_day_constraint(solver)


# ---------------------------------------------------------------------------
# Resource-Specific No-Overlap
# ---------------------------------------------------------------------------

def _add_teacher_no_overlap(solver: 'SchedulerSolver') -> None:
    """Each teacher teaches at most one lecture at a time."""
    for tid in solver.teacher_courses:
        intervals = [
            lec.teacher_opt_intervals[tid]
            for lec in solver.lectures
            if tid in lec.teacher_opt_intervals
        ]
        if intervals:
            solver.model.AddNoOverlap(intervals)


def _add_room_no_overlap(solver: 'SchedulerSolver') -> None:
    """Each room hosts at most one lecture at a time."""
    for room in solver.rooms:
        intervals = [
            lec.room_opt_intervals[room.id]
            for lec in solver.lectures
            if room.id in lec.room_opt_intervals
        ]
        if intervals:
            solver.model.AddNoOverlap(intervals)


def _add_student_no_overlap(solver: 'SchedulerSolver') -> None:
    """Each student attends at most one lecture at a time."""
    for student_id, course_ids in solver.student_courses.items():
        if len(course_ids) < 2:
            continue
        intervals = [
            lec.interval
            for lec in solver.lectures
            if lec.course.id in course_ids
        ]
        if intervals:
            solver.model.AddNoOverlap(intervals)


# ---------------------------------------------------------------------------
# Availability Constraints
# ---------------------------------------------------------------------------

def _add_availability_constraints(solver: 'SchedulerSolver') -> None:
    """
    Wire pre-built availability before/after literals.
    
    For each lecture's availability literals:
    - Student: SOFT. Must be before OR after, OR the lecture pays a
      penalty (SolverWeights.student_availability_violation) in the
      objective. A hard, unconditional requirement that every enrolled
      student be free for every lecture of a course is unsatisfiable for
      any sufficiently large/diverse class (proven: ~80% of courses in
      the current mock dataset have zero common free slot across all
      enrolled students). Making it soft is what lets the solver return
      an actual schedule -- minimizing conflicts -- instead of
      INFEASIBLE, matching how production university timetabling
      systems typically treat student availability.
    - Teacher: HARD. If assigned to that teacher, must be before OR after.
    - Room: HARD. If assigned to that room, must be before OR after.
    
    Uses clean AvailabilityLiteral objects with explicit entity_type,
    entity_id fields — no string parsing needed.
    """
    for lec in solver.lectures:
        for al in lec.availability_literals:
            if al.entity_type == 'student':
                # Soft: before OR after OR (penalized) violation
                violation = solver.model.NewBoolVar(
                    f"sav_{al.entity_id}_{al.availability_index}_"
                    f"{lec.course.id}_{lec.lecture_number}"
                )
                solver.model.AddBoolOr([al.before, al.after, violation])
                solver.student_availability_violations.append(violation)
            
            elif al.entity_type == 'teacher':
                # Hard, conditional: only if assigned to this teacher
                presence = lec.teacher_presence.get(al.entity_id)
                if presence is not None:
                    solver.model.AddBoolOr([al.before, al.after, presence.Not()])
            
            elif al.entity_type == 'room':
                # Hard, conditional: only if assigned to this room
                presence = lec.room_presence.get(al.entity_id)
                if presence is not None:
                    solver.model.AddBoolOr([al.before, al.after, presence.Not()])


# ---------------------------------------------------------------------------
# Same-Day Constraint
# ---------------------------------------------------------------------------

def _add_same_day_constraint(solver: 'SchedulerSolver') -> None:
    """If enabled, lectures of the same course must be on different days."""
    if not solver.config.prevent_same_day:
        return
    
    for course in solver.courses:
        if course.lectures_per_week <= 1:
            continue
        course_days = [
            lec.day
            for lec in solver.lectures
            if lec.course.id == course.id
        ]
        if len(course_days) >= 2:
            solver.model.AddAllDifferent(course_days)
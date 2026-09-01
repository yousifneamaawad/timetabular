#mock data generator doesnt read from database it uses 12peroids config on it on

#!/usr/bin/env python3
"""
Mock data generator for the university scheduling system.
Generates realistic, CP-SAT-compatible test data.

CRITICAL DESIGN DECISIONS:
- All availability tables store AVAILABLE periods (NOT unavailability)
- Course titles are unique per department (not globally)
- Teacher assignment gracefully handles full capacity
- Room generation matches course demand patterns
- No mock schedule generation (use actual solver output)

Usage:
    python generate_mock_data.py --difficulty hard
    python generate_mock_data.py --students 2500 --rooms 50 --teachers 40
"""

import sqlite3
import random
import argparse
import json
import sys
import math
import re
from pathlib import Path
from typing import Optional, List, Dict, Set, Tuple
from collections import defaultdict, Counter
from dataclasses import dataclass
from datetime import datetime
import logging

sys.path.insert(0, str(Path(__file__).parent))
from database import db_manager

# ============================================================================
# CONFIGURATION
# ============================================================================

@dataclass
class GenerationConfig:
    """Configuration for data generation."""
    student_count: int = 1000
    teacher_count: int = 100
    room_count: int = 60
    course_count: int = 120
    
    difficulty: str = "normal"
    
    min_courses_per_student: int = 4
    max_courses_per_student: int = 7
    max_courses_per_teacher: int = 6
    enrollment_dept_ratio: float = 0.75
    cross_dept_teaching: float = 0.10
    preferred_room_rate: float = 0.40
    working_student_ratio: float = 0.15
    retake_ratio: float = 0.05
    elective_ratio: float = 0.15
    
    slots_per_day: int = 12
    days_per_week: int = 5
    
    seed: int = 42
    db_path: str = "scheduler.db"

# ============================================================================
# CONSTANTS
# ============================================================================

DEPARTMENTS = [
    "Computer Science",
    "Business Administration",
    "Mechanical Engineering",
    "Digital Arts",
    "Mathematics",
    "Physics"
]

DEPT_WEIGHTS = [0.25, 0.20, 0.18, 0.12, 0.15, 0.10]
YEAR_WEIGHTS = [0.30, 0.25, 0.20, 0.15, 0.10]

# Building-department mapping for intelligent room assignment
DEPT_BUILDINGS = {
    "Computer Science": ["CS Building"],
    "Business Administration": ["Business Hall"],
    "Mechanical Engineering": ["Engineering Block"],
    "Digital Arts": ["Arts Complex"],
    "Mathematics": ["Mathematics Building"],
    "Physics": ["Physics Laboratory", "Science Wing"],
}

# Teacher availability patterns (ALL represent AVAILABLE times)
TEACHER_AVAILABILITY_PATTERNS = [
    # Morning person: available periods 1-8
    {"Mon": [(1, 8)], "Tue": [(1, 8)], "Wed": [(1, 8)], "Thu": [(1, 8)], "Fri": [(1, 6)]},
    # Afternoon person: available periods 4-12
    {"Mon": [(4, 12)], "Tue": [(4, 12)], "Wed": [(4, 12)], "Thu": [(4, 12)], "Fri": []},
    # Split schedule with Wednesday meetings
    {"Mon": [(1, 5), (7, 12)], "Tue": [(1, 5), (7, 12)], "Wed": [(3, 10)], 
     "Thu": [(1, 5), (7, 12)], "Fri": [(1, 5)]},
    # Part-time: Mon/Wed/Fri mornings only
    {"Mon": [(1, 8)], "Tue": [], "Wed": [(1, 8)], "Thu": [], "Fri": [(1, 6)]},
    # Early bird: periods 1-6
    {"Mon": [(1, 6)], "Tue": [(1, 6)], "Wed": [(1, 6)], "Thu": [(1, 6)], "Fri": [(1, 4)]},
    # Night owl: periods 6-12
    {"Mon": [(6, 12)], "Tue": [(6, 12)], "Wed": [(6, 12)], "Thu": [(6, 12)], "Fri": [(4, 12)]},
    # Full availability
    {"Mon": [(1, 12)], "Tue": [(1, 12)], "Wed": [(1, 12)], "Thu": [(1, 12)], "Fri": [(1, 12)]},
]

def _base_course_title(title: str) -> str:
    """
    Strip a trailing ' (Section X)' so different sections of the same
    course collapse to one identity for enrollment-dedup purposes.
    Courses with no section suffix are returned unchanged, which also
    correctly catches the case of two distinct course rows that happen
    to share an identical title (e.g. two independently-generated
    "Topics in X" courses).
    """
    return re.sub(r'\s*\(Section [A-Za-z0-9]+\)\s*$', '', title).strip()


# Student availability patterns (ALL represent AVAILABLE times)
STUDENT_AVAILABILITY_PATTERNS = [
    # Full-time: available all day
    {"Mon": [(1, 12)], "Tue": [(1, 12)], "Wed": [(1, 12)], "Thu": [(1, 12)], "Fri": [(1, 8)]},
    # Morning student: available periods 1-7
    {"Mon": [(1, 7)], "Tue": [(1, 7)], "Wed": [(1, 7)], "Thu": [(1, 7)], "Fri": [(1, 5)]},
    # Afternoon student: available periods 4-12
    {"Mon": [(4, 12)], "Tue": [(4, 12)], "Wed": [(4, 12)], "Thu": [(4, 12)], "Fri": [(3, 8)]},
    # Working student: evenings only
    {"Mon": [], "Tue": [(5, 12)], "Wed": [], "Thu": [(5, 12)], "Fri": [(5, 12)]},
    # Early classes only: periods 1-4
    {"Mon": [(1, 4)], "Tue": [(1, 4)], "Wed": [(1, 4)], "Thu": [(1, 4)], "Fri": [(1, 4)]},
]
# NOTE: the archetype patterns above are kept only because teacher_patterns
# still uses TEACHER_AVAILABILITY_PATTERNS for an unrelated bookkeeping
# dict. generate_availabilities() no longer draws from either list -- see
# _sparse_available_windows() below. The archetypes were mutually
# exclusive by construction (e.g. "Early classes only" = periods 1-4 vs.
# "Working student" = periods 5-12, zero shared period), which meant any
# class mixing students from both patterns had zero common free slot --
# proven to affect ~80% of courses in generated datasets. Real students
# have a handful of specific personal conflicts, not an all-day archetype.


def _sparse_available_windows(
    spd: int,
    dpw: int,
    full_day_off_prob: float = 0.03,
    gap_prob: float = 0.15,
    gap_len_range: tuple = (1, 2),
) -> list:
    """
    Generate a realistic, mostly-available weekly schedule for one entity:
    every day is fully available by default; each day independently has a
    small chance of one short personal-conflict gap, and a rare chance of
    being unavailable the entire day. Returns (day, start_period,
    end_period) AVAILABLE window tuples, day-numbered 1..dpw -- the same
    format the DB tables store and _invert_availability() (solver.py)
    expects as input.

    Tuned so a typical entity ends up available on the large majority of
    periods across the week (roughly 85-97% depending on the probabilities
    passed in), instead of the old archetypes which could exclude entire
    half-weeks or whole period ranges (e.g. "evenings only").
    """
    windows = []
    for day in range(1, dpw + 1):
        if random.random() < full_day_off_prob:
            continue  # no window recorded -> unavailable this whole day

        if random.random() >= gap_prob:
            windows.append((day, 1, spd))
            continue

        gap_len = min(random.randint(*gap_len_range), spd)
        gap_start = random.randint(1, spd - gap_len + 1)
        gap_end = gap_start + gap_len - 1

        if gap_start > 1:
            windows.append((day, 1, gap_start - 1))
        if gap_end < spd:
            windows.append((day, gap_end + 1, spd))
        # if the gap happens to cover the entire day, no window is added
        # for that day, which correctly means "unavailable all day".

    return windows



# Complete course catalog with course codes
COURSE_CATALOG = {
    "Computer Science": [
        ("CS101", "Introduction to Programming", 1, 3, 1, False, 60, 120, 3),
        ("CS102", "Data Structures", 1, 3, 1, False, 60, 120, 2),
        ("CS201", "Algorithms", 2, 3, 1, False, 50, 100, 2),
        ("CS202", "Database Systems", 2, 3, 1, False, 50, 100, 2),
        ("CS301", "Operating Systems", 3, 2, 1, False, 40, 80, 2),
        ("CS302", "Computer Networks", 3, 3, 1, False, 40, 80, 1),
        ("CS401", "Software Engineering", 4, 2, 1, False, 30, 60, 2),
        ("CS402", "Machine Learning", 4, 2, 1, False, 30, 60, 1),
        ("CS403", "Artificial Intelligence", 4, 2, 1, False, 30, 60, 1),
        ("CS404", "Cybersecurity", 4, 2, 1, False, 30, 60, 1),
    ],
    "Business Administration": [
        ("BUS101", "Principles of Management", 1, 3, 1, False, 60, 120, 3),
        ("BUS102", "Marketing Fundamentals", 1, 3, 1, False, 60, 120, 2),
        ("BUS103", "Financial Accounting", 1, 3, 1, False, 60, 120, 2),
        ("BUS201", "Business Ethics", 2, 2, 1, False, 40, 80, 1),
        ("BUS202", "Organizational Behavior", 2, 3, 1, False, 40, 80, 1),
        ("BUS301", "Strategic Management", 3, 2, 1, False, 30, 60, 2),
        ("BUS302", "International Business", 3, 2, 1, False, 30, 60, 1),
        ("BUS401", "Entrepreneurship", 4, 2, 1, False, 25, 50, 1),
        ("BUS402", "Corporate Finance", 4, 2, 1, False, 25, 50, 1),
    ],
    "Mechanical Engineering": [
        ("ME101", "Statics", 1, 3, 1, False, 50, 100, 2),
        ("ME102", "Dynamics", 1, 3, 1, False, 50, 100, 2),
        ("ME201", "Thermodynamics", 2, 2, 1, False, 40, 80, 2),
        ("ME202", "Fluid Mechanics", 2, 3, 1, False, 40, 80, 1),
        ("ME301", "Materials Science", 3, 2, 2, True, 30, 50, 2),
        ("ME302", "Machine Design", 3, 2, 2, True, 30, 50, 1),
        ("ME303", "Heat Transfer", 3, 2, 1, False, 30, 60, 1),
        ("ME401", "Robotics", 4, 2, 2, True, 20, 40, 1),
    ],
    "Digital Arts": [
        ("DA101", "Digital Imaging", 1, 3, 2, True, 30, 50, 2),
        ("DA102", "Graphic Design", 1, 3, 2, True, 30, 50, 2),
        ("DA201", "Web Design", 2, 3, 2, True, 25, 45, 1),
        ("DA202", "Video Production", 2, 2, 2, True, 25, 45, 1),
        ("DA301", "3D Modeling", 3, 2, 2, True, 20, 35, 1),
        ("DA302", "Digital Animation", 3, 2, 2, True, 20, 35, 1),
        ("DA401", "Game Design", 4, 2, 2, True, 15, 30, 1),
        ("DA402", "UI/UX Design", 4, 2, 1, False, 15, 30, 1),
    ],
    "Mathematics": [
        ("MATH101", "Calculus I", 1, 4, 1, False, 60, 120, 4),
        ("MATH102", "Calculus II", 1, 4, 1, False, 60, 120, 3),
        ("MATH201", "Linear Algebra", 2, 3, 1, False, 50, 100, 2),
        ("MATH202", "Differential Equations", 2, 3, 1, False, 40, 80, 2),
        ("MATH301", "Probability", 3, 3, 1, False, 30, 60, 1),
        ("MATH302", "Statistics", 3, 3, 1, False, 30, 60, 1),
        ("MATH401", "Numerical Methods", 4, 2, 1, False, 20, 40, 1),
    ],
    "Physics": [
        ("PHY101", "Mechanics", 1, 3, 2, True, 50, 100, 2),
        ("PHY102", "Electromagnetism", 1, 3, 2, True, 50, 100, 2),
        ("PHY201", "Thermodynamics", 2, 3, 1, False, 40, 80, 1),
        ("PHY202", "Optics", 2, 3, 2, True, 35, 70, 1),
        ("PHY301", "Quantum Physics", 3, 2, 1, False, 25, 50, 1),
        ("PHY302", "Nuclear Physics", 3, 2, 1, False, 25, 50, 1),
        ("PHY401", "Astrophysics", 4, 2, 1, False, 15, 30, 1),
    ]
}

FIRST_NAMES = [
    "James", "Mary", "John", "Patricia", "Robert", "Jennifer", "Michael", "Linda",
    "William", "Elizabeth", "David", "Barbara", "Richard", "Susan", "Joseph", "Jessica",
    "Thomas", "Sarah", "Charles", "Karen", "Christopher", "Nancy", "Daniel", "Lisa",
    "Matthew", "Betty", "Anthony", "Helen", "Mark", "Sandra", "Donald", "Donna"
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Wilson", "Anderson", "Thomas",
    "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson", "White",
    "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker", "Young"
]

# ============================================================================
# MOCK DATA GENERATOR
# ============================================================================

class MockDataGenerator:
    """Generates CP-SAT-compatible mock data with clear availability semantics."""
    
    def __init__(self, config: GenerationConfig):
        self.config = config
        self.logger = self._setup_logging()
        self._apply_difficulty()
        
        # Storage
        self.students: List[Dict] = []
        self.teachers: List[Dict] = []
        self.rooms: List[Dict] = []
        self.courses: List[Dict] = []
        
        # Lookups
        self.dept_teachers: Dict[str, List[int]] = defaultdict(list)
        self.room_types: Dict[str, List[int]] = defaultdict(list)
        self.room_capacities: Dict[int, int] = {}
        self.room_buildings: Dict[int, str] = {}
        self.teacher_patterns: Dict[int, Dict] = {}
        
        # Caches
        self.course_cache: Dict[int, Dict] = {}
        self.teacher_workload: Counter = Counter()
        
        # Uniqueness (department, title) for courses
        self.used_course_keys: Set[Tuple[str, str]] = set()
        self.used_emails: Set[str] = set()
        self.used_names: Set[str] = set()
        self.used_rooms: Set[str] = set()
        
        # Demand tracking
        self.lab_course_count = 0
        self.lecture_course_count = 0
    
    def _apply_difficulty(self) -> None:
        """Adjust parameters for difficulty level."""
        if self.config.difficulty == "hard":
            self.config.course_count = int(self.config.course_count * 1.5)
            self.config.room_count = int(self.config.room_count * 0.7)
            self.config.teacher_count = int(self.config.teacher_count * 0.6)
            self.config.working_student_ratio = 0.25
            self.config.retake_ratio = 0.10
            self.config.cross_dept_teaching = 0.20
        elif self.config.difficulty == "easy":
            self.config.room_count = int(self.config.room_count * 1.5)
            self.config.teacher_count = int(self.config.teacher_count * 1.3)
            self.config.working_student_ratio = 0.05
    
    def _setup_logging(self) -> logging.Logger:
        logging.basicConfig(level=logging.INFO,
                          format='%(asctime)s - %(levelname)-8s - %(message)s',
                          datefmt='%H:%M:%S')
        return logging.getLogger(__name__)
    
    # ========================================================================
    # GENERATION METHODS
    # ========================================================================
    
    def clear_database(self) -> None:
        """Clear all data respecting foreign keys."""
        self.logger.info("Clearing database...")
        with db_manager.get_connection() as conn:
            for table in ["schedule", "student_availability", "teacher_availability",
                         "room_availability", "enrollment", "teacher_assignments",
                         "courses", "rooms", "teachers", "students"]:
                conn.execute(f"DELETE FROM {table}")
                conn.execute(f"DELETE FROM sqlite_sequence WHERE name='{table}'")
            conn.commit()
    
    def generate_students(self) -> None:
        """Generate students with year distribution and retake tracking."""
        self.logger.info(f"Generating {self.config.student_count} students...")
        
        batch = []
        for _ in range(self.config.student_count):
            dept = random.choices(DEPARTMENTS, weights=DEPT_WEIGHTS)[0]
            
            if random.random() < self.config.retake_ratio:
                year = random.choices([1, 2, 3, 4], weights=[0.4, 0.3, 0.2, 0.1])[0]
            else:
                year = random.choices([1, 2, 3, 4, 5], weights=YEAR_WEIGHTS)[0]
            
            name = self._unique_name()
            email = self._unique_email(name)
            batch.append((name, dept, year, email))
            
            if len(batch) >= 500:
                self._batch_insert('students',
                    '(full_name, department, year_level, email) VALUES (?, ?, ?, ?)', batch)
                batch.clear()
        
        if batch:
            self._batch_insert('students',
                '(full_name, department, year_level, email) VALUES (?, ?, ?, ?)', batch)
        
        self._load_students()
        self.logger.info(f"  ✓ {len(self.students)} students")
    
    def generate_teachers(self) -> None:
        """
        Generate teachers ensuring enough for course demand.
        Calculates minimum required: ceil(courses / max_per_teacher)
        """
        min_teachers = math.ceil(self.config.course_count / self.config.max_courses_per_teacher)
        actual_count = max(self.config.teacher_count, min_teachers)
        
        if actual_count > self.config.teacher_count:
            self.logger.warning(f"  Increasing teachers {self.config.teacher_count} → {actual_count}")
            self.config.teacher_count = actual_count
        
        self.logger.info(f"Generating {self.config.teacher_count} teachers...")
        
        batch = []
        for _ in range(self.config.teacher_count):
            dept = random.choices(DEPARTMENTS, weights=DEPT_WEIGHTS)[0]
            name = self._unique_name()
            email = self._unique_email(name)
            batch.append((name, dept, email))
        
        self._batch_insert('teachers',
            '(full_name, department, email) VALUES (?, ?, ?)', batch)
        
        self._load_teachers()
        
        # Assign availability patterns
        for teacher in self.teachers:
            self.teacher_patterns[teacher['id']] = random.choice(TEACHER_AVAILABILITY_PATTERNS)
        
        self.logger.info(f"  ✓ {len(self.teachers)} teachers (min: {min_teachers})")
    
    def generate_rooms(self) -> None:
        """
        Generate rooms proportional to course requirements.
        Counts lab vs lecture courses and allocates rooms accordingly.
        Names include building prefix: CS-101, ENG-205, etc.
        """
        self.logger.info(f"Generating {self.config.room_count} rooms...")
        
        # Calculate demand
        lab_courses = sum(1 for dept_courses in COURSE_CATALOG.values()
                         for _, _, _, _, _, lab, _, _, _ in dept_courses if lab)
        lecture_courses = sum(1 for dept_courses in COURSE_CATALOG.values()
                            for _, _, _, _, _, lab, _, _, _ in dept_courses if not lab)
        
        total = max(lab_courses + lecture_courses, 1)
        lab_ratio = lab_courses / total
        
        lab_rooms = max(int(self.config.room_count * lab_ratio * 1.2), 1)
        computer_lab_rooms = max(int(self.config.room_count * 0.15), 1)
        seminar_rooms = max(int(self.config.room_count * 0.20), 1)
        lecture_rooms = self.config.room_count - lab_rooms - computer_lab_rooms - seminar_rooms
        
        self.logger.info(f"  Allocation: {lecture_rooms} Lecture, {seminar_rooms} Seminar, "
                        f"{lab_rooms} Lab, {computer_lab_rooms} Computer Lab")
        
        room_configs = [
            ("Lecture", lecture_rooms, 60, 150),
            ("Seminar", seminar_rooms, 20, 40),
            ("Laboratory", lab_rooms, 25, 80),
            ("Computer Lab", computer_lab_rooms, 25, 80),
        ]
        
        # Building prefixes for room names
        building_prefixes = {
            "CS": "Computer Science Building",
            "BUS": "Business Hall",
            "ENG": "Engineering Block",
            "ART": "Arts Complex",
            "MATH": "Mathematics Building",
            "PHY": "Physics Laboratory",
        }
        
        batch = []
        room_counter = defaultdict(lambda: defaultdict(int))
        
        for room_type, count, cap_min, cap_max in room_configs:
            # Assign prefixes based on room type
            if room_type == "Computer Lab":
                prefixes = ["CS", "BUS", "ART"]
            elif room_type == "Laboratory":
                prefixes = ["CS", "ENG", "PHY"]
            elif room_type == "Seminar":
                prefixes = ["BUS", "ART", "MATH"]
            else:
                prefixes = list(building_prefixes.keys())
            
            for _ in range(count):
                prefix = random.choice(prefixes)
                floor = random.randint(1, 4)
                room_counter[prefix][floor] += 1
                name = f"{prefix}-{floor}{room_counter[prefix][floor]:02d}"
                
                while name in self.used_rooms:
                    room_counter[prefix][floor] += 1
                    name = f"{prefix}-{floor}{room_counter[prefix][floor]:02d}"
                
                self.used_rooms.add(name)
                capacity = random.randint(cap_min, cap_max)
                building = building_prefixes[prefix]
                
                batch.append((name, capacity, room_type, building, floor))
        
        self._batch_insert('rooms',
            '(room_name, capacity, room_type, building, floor) VALUES (?, ?, ?, ?, ?)',
            batch[:self.config.room_count])
        
        self._load_rooms()
        self.logger.info(f"  ✓ {len(self.rooms)} rooms")
    
    def generate_courses(self) -> None:
        """
        Generate courses with course codes.
        Uniqueness is per (department, title) not global.
        """
        self.logger.info(f"Generating courses (target: {self.config.course_count})...")
        
        batch = []
        self.lab_course_count = 0
        self.lecture_course_count = 0
        
        for dept, courses in COURSE_CATALOG.items():
            for code, title, year, lectures, duration, lab, min_s, max_s, sections in courses:
                for section_num in range(sections):
                    if len(batch) >= self.config.course_count:
                        break
                    
                    key = (dept, title)
                    if key not in self.used_course_keys:
                        self.used_course_keys.add(key)
                    
                    base_students = random.randint(min_s, max_s)
                    section_students = max(base_students // sections, 5)
                    section_title = title if sections == 1 else f"{title} (Section {chr(65+section_num)})"
                    
                    batch.append((section_title, dept, year, lectures, duration,
                                section_students, lab))
                    
                    if lab:
                        self.lab_course_count += 1
                    else:
                        self.lecture_course_count += 1
        
        # Generate additional if catalog exhausted
        while len(batch) < self.config.course_count:
            dept = random.choice(DEPARTMENTS)
            year = random.choices([1, 2, 3, 4], weights=[0.3, 0.3, 0.25, 0.15])[0]
            title = f"Topics in {dept} {random.choice(['I', 'II', 'III'])}"
            lab = random.random() < 0.25
            lectures = random.choice([2, 3, 4]) if not lab else 2
            duration = 2 if lab else random.choice([1, 2])
            students = random.randint(20, 80)
            
            batch.append((title, dept, year, lectures, duration, students, lab))
            
            if lab:
                self.lab_course_count += 1
            else:
                self.lecture_course_count += 1
        
        self._batch_insert('courses',
            """(title, department, year_level, lectures_per_week, duration,
               students_per_lecture, requires_lab)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            batch[:self.config.course_count])
        
        self._load_courses()
        self.logger.info(f"  ✓ {len(self.courses)} courses "
                        f"({self.lab_course_count} lab, {self.lecture_course_count} lecture)")
    
    def assign_teachers(self) -> None:
        """
        Assign teachers with cross-department teaching.
        GUARANTEED to never fail - allows overload when all teachers at capacity.
        """
        self.logger.info("Assigning teachers...")
        
        if not self.teachers or not self.courses:
            return
        
        # Group courses by department
        dept_courses = defaultdict(list)
        for course in self.courses:
            dept_courses[course['department']].append(course)
        
        assignments = []
        overload_warning = False
        
        for dept, courses in dept_courses.items():
            dept_teachers = self.dept_teachers.get(dept, [])
            available = dept_teachers.copy() if dept_teachers else [t['id'] for t in self.teachers]
            
            for course in courses:
                # Cross-department teaching
                if (random.random() < self.config.cross_dept_teaching and
                    len(self.teachers) > len(dept_teachers)):
                    other_teachers = [t['id'] for t in self.teachers
                                    if t['department'] != dept]
                    if other_teachers and random.random() < 0.5:
                        available = other_teachers
                
                # GUARANTEED: never let available be empty
                if not available:
                    available = [t['id'] for t in self.teachers]
                    if not overload_warning:
                        self.logger.warning("  All teachers at capacity - allowing overload")
                        overload_warning = True
                
                # Safety check (should never happen)
                if not available:
                    raise RuntimeError("No teachers available for assignment!")
                
                teacher_id = min(available, key=lambda tid: self.teacher_workload[tid])
                
                # Intelligent room preference based on department
                preferred_room = self._intelligent_room_preference(course, dept)
                
                assignments.append((teacher_id, course['id'], preferred_room))
                self.teacher_workload[teacher_id] += 1
                
                # Remove overloaded teachers only if alternatives exist
                if (self.teacher_workload[teacher_id] >= self.config.max_courses_per_teacher
                    and len(available) > 1):
                    available.remove(teacher_id)
        
        with db_manager.get_connection() as conn:
            conn.executemany(
                """INSERT INTO teacher_assignments (teacher_id, course_id, preferred_room_id)
                   VALUES (?, ?, ?)""", assignments)
            conn.commit()
        
        # Statistics
        cross_dept = 0
        for t_id, c_id, _ in assignments:
            teacher_dept = next((t['department'] for t in self.teachers if t['id'] == t_id), None)
            course_dept = self.course_cache[c_id]['department']
            if teacher_dept != course_dept:
                cross_dept += 1
        
        self.logger.info(f"  ✓ {len(assignments)} assignments "
                        f"(cross-dept: {cross_dept}, {100*cross_dept/len(assignments):.1f}%)")
    
    def _intelligent_room_preference(self, course: Dict, dept: str) -> Optional[int]:
        """
        Choose preferred room biased toward:
        1. Department's building
        2. Correct room type (lab vs lecture)
        3. Sufficient capacity
        """
        if random.random() > self.config.preferred_room_rate:
            return None
        
        title = course.get('title', '').lower()
        requires_lab = course.get('requires_lab', False)
        students = course.get('students_per_lecture', 0)
        
        # Determine preferred room types
        if requires_lab:
            if any(kw in title for kw in ["computer", "programming", "data", "digital"]):
                preferred_types = ["Computer Lab"]
            else:
                preferred_types = ["Laboratory", "Computer Lab"]
        elif any(kw in title for kw in ["seminar", "discussion", "workshop"]):
            preferred_types = ["Seminar"]
        else:
            preferred_types = ["Lecture", "Seminar"]
        
        # Find matching rooms, bias toward department buildings
        dept_buildings = DEPT_BUILDINGS.get(dept, [])
        
        candidates = []
        for room_type in preferred_types:
            for room_id in self.room_types.get(room_type, []):
                if self.room_capacities.get(room_id, 0) >= students:
                    # Bonus points for department building
                    building = self.room_buildings.get(room_id, "")
                    if building in dept_buildings:
                        candidates.extend([room_id] * 3)  # 3x weight
                    else:
                        candidates.append(room_id)  # 1x weight
        
        return random.choice(candidates) if candidates else None
    
    def generate_enrollments(self) -> None:
        """
        Generate enrollments with electives and retakes.

        A student must never end up enrolled in two different SECTIONS of
        the same course (e.g. "Data Structures (Section A)" and
        "Data Structures (Section B)") -- that's not a real registration
        pattern, and it silently created thousands of unavoidable
        same-time conflicts (proven: 95% of enrolled students had at
        least one double-booking once this was allowed). Sections share
        a base title differing only by the trailing "(Section X)", so
        base-title dedup is enough to prevent it, and it also correctly
        prevents the separate case of two distinct courses that happen to
        share an identical (un-suffixed) title.
        """
        self.logger.info("Generating enrollments...")
        
        if not self.students or not self.courses:
            return
        
        course_by_dept_year = defaultdict(lambda: defaultdict(list))
        for course in self.courses:
            course_by_dept_year[course['department']][course['year_level']].append(course)
        
        enrollments = []
        course_enrollment = Counter()
        elective_count = 0
        retake_count = 0
        
        for student in self.students:
            dept = student['department']
            year = student['year_level']
            num_courses = random.randint(self.config.min_courses_per_student,
                                        self.config.max_courses_per_student)
            
            selected = set()
            selected_base_titles = set()
            
            # Department courses
            dept_courses = course_by_dept_year.get(dept, {}).get(year, [])
            num_dept = int(num_courses * (1 - self.config.elective_ratio))
            
            if dept_courses:
                dept_courses.sort(key=lambda c: course_enrollment[c['id']] /
                                               max(c['students_per_lecture'], 1))
                for course in dept_courses:
                    if len(selected) >= num_dept:
                        break
                    base_title = _base_course_title(course['title'])
                    if base_title in selected_base_titles:
                        continue
                    if course_enrollment[course['id']] < course['students_per_lecture']:
                        selected.add(course['id'])
                        selected_base_titles.add(base_title)
            
            # Retake courses
            if random.random() < self.config.retake_ratio and year > 1:
                retake_courses = course_by_dept_year.get(dept, {}).get(year - 1, [])
                if retake_courses:
                    available = [c for c in retake_courses
                               if course_enrollment[c['id']] < c['students_per_lecture']
                               and _base_course_title(c['title']) not in selected_base_titles]
                    if available:
                        chosen = random.choice(available)
                        selected.add(chosen['id'])
                        selected_base_titles.add(_base_course_title(chosen['title']))
                        retake_count += 1
            
            # Electives
            remaining = num_courses - len(selected)
            if remaining > 0:
                other_courses = [c for c in self.courses
                               if c['department'] != dept and
                               course_enrollment[c['id']] < c['students_per_lecture'] and
                               _base_course_title(c['title']) not in selected_base_titles]
                if other_courses:
                    random.shuffle(other_courses)
                    for course in other_courses:
                        if len(selected) >= num_courses:
                            break
                        base_title = _base_course_title(course['title'])
                        if base_title in selected_base_titles:
                            continue
                        selected.add(course['id'])
                        selected_base_titles.add(base_title)
                        elective_count += 1
            
            for course_id in selected:
                enrollments.append((student['id'], course_id))
                course_enrollment[course_id] += 1
        
        with db_manager.get_connection() as conn:
            conn.executemany(
                "INSERT INTO enrollment (student_id, course_id) VALUES (?, ?)",
                enrollments)
            conn.commit()
        
        self.logger.info(f"  ✓ {len(enrollments)} enrollments "
                        f"(electives: {elective_count}, retakes: {retake_count})")
        
        if self.courses:
            ratios = [course_enrollment[c['id']] / max(c['students_per_lecture'], 1)
                     for c in self.courses if c['students_per_lecture'] > 0]
            if ratios:
                self.logger.info(f"  Enrollment ratio: {min(ratios):.2f} - {max(ratios):.2f} "
                               f"(avg: {sum(ratios)/len(ratios):.2f})")
    
    def generate_availabilities(self) -> None:
        """
        Generate AVAILABILITY records.
        
        CRITICAL: All records represent periods when the entity IS AVAILABLE.
        Students, teachers, and rooms all use the same semantics.
        """
        self.logger.info("Generating availability records...")
        
        student_avail = []
        teacher_avail = []
        room_avail = []
        
        spd = self.config.slots_per_day
        dpw = self.config.days_per_week
        
        # STUDENT AVAILABILITY: mostly available, with a minority of
        # "working students" who have meaningfully less time but are
        # still not mutually exclusive with everyone else's schedule.
        for student in self.students:
            if random.random() < self.config.working_student_ratio:
                windows = _sparse_available_windows(
                    spd, dpw, full_day_off_prob=0.15, gap_prob=0.40,
                    gap_len_range=(2, 4),
                )
            else:
                windows = _sparse_available_windows(
                    spd, dpw, full_day_off_prob=0.03, gap_prob=0.15,
                    gap_len_range=(1, 2),
                )
            for day, start, end in windows:
                student_avail.append((student['id'], day, start, end))
        
        # TEACHER AVAILABILITY: teachers are on campus nearly all week,
        # with occasional small personal-conflict blocks.
        for teacher in self.teachers:
            windows = _sparse_available_windows(
                spd, dpw, full_day_off_prob=0.02, gap_prob=0.10,
                gap_len_range=(1, 2),
            )
            for day, start, end in windows:
                teacher_avail.append((teacher['id'], day, start, end))
        
        # ROOM AVAILABILITY (mostly available, occasional maintenance gap)
        for room in self.rooms:
            for day in range(1, dpw + 1):
                if random.random() < 0.95:
                    room_avail.append((room['id'], day, 1, spd))
                else:
                    # Maintenance creates a gap - store available periods
                    # around it. gap_end is exclusive-of-nothing here (it's
                    # the last blocked period), so the "after" window must
                    # start at gap_end + 1, not gap_end, or the gap never
                    # actually blocks anything.
                    gap_len = random.randint(1, 2)
                    gap_start = random.randint(2, max(2, spd - gap_len))
                    gap_end = gap_start + gap_len - 1
                    if gap_start > 1:
                        room_avail.append((room['id'], day, 1, gap_start - 1))
                    if gap_end < spd:
                        room_avail.append((room['id'], day, gap_end + 1, spd))
        
        with db_manager.get_connection() as conn:
            if student_avail:
                conn.executemany(
                    """INSERT INTO student_availability (entity_id, day, start_period, end_period)
                       VALUES (?, ?, ?, ?)""", student_avail)
            if teacher_avail:
                conn.executemany(
                    """INSERT INTO teacher_availability (entity_id, day, start_period, end_period)
                       VALUES (?, ?, ?, ?)""", teacher_avail)
            if room_avail:
                conn.executemany(
                    """INSERT INTO room_availability (entity_id, day, start_period, end_period)
                       VALUES (?, ?, ?, ?)""", room_avail)
            conn.commit()
        
        self.logger.info(f"  ✓ {len(student_avail)} student, {len(teacher_avail)} teacher, "
                        f"{len(room_avail)} room availability records")
        self.logger.info(f"  Student avg blocks: {len(student_avail)/max(len(self.students),1):.1f}")
        self.logger.info(f"  Teacher avg blocks: {len(teacher_avail)/max(len(self.teachers),1):.1f}")
    
    # ========================================================================
    # VALIDATION
    # ========================================================================
    
    def validate(self) -> bool:
        """Comprehensive validation including availability semantics checks."""
        self.logger.info("\n" + "="*60)
        self.logger.info("VALIDATION")
        self.logger.info("="*60)
        
        valid = True
        
        with db_manager.get_connection() as conn:
            checks = [
                ("Courses without teachers",
                 """SELECT COUNT(*) FROM courses c
                    LEFT JOIN teacher_assignments ta ON c.id=ta.course_id
                    WHERE ta.course_id IS NULL"""),
                ("Orphan enrollments",
                 """SELECT COUNT(*) FROM enrollment e
                    LEFT JOIN students s ON e.student_id=s.id
                    WHERE s.id IS NULL"""),
                ("Duplicate student emails",
                 "SELECT email, COUNT(*) FROM students GROUP BY email HAVING COUNT(*)>1"),
                ("Duplicate teacher emails",
                 "SELECT email, COUNT(*) FROM teachers GROUP BY email HAVING COUNT(*)>1"),
                ("Duplicate room names",
                 "SELECT room_name, COUNT(*) FROM rooms GROUP BY room_name HAVING COUNT(*)>1"),
                ("Invalid preferred rooms",
                 """SELECT COUNT(*) FROM teacher_assignments ta
                    WHERE ta.preferred_room_id IS NOT NULL
                    AND NOT EXISTS (SELECT 1 FROM rooms r WHERE r.id=ta.preferred_room_id)"""),
                ("Rooms too small for courses",
                 """SELECT COUNT(*) FROM courses c
                    WHERE NOT EXISTS (
                        SELECT 1 FROM rooms r
                        WHERE r.capacity >= c.students_per_lecture
                        AND ((c.requires_lab AND r.room_type IN ('Laboratory','Computer Lab'))
                             OR (NOT c.requires_lab AND r.room_type IN ('Lecture','Seminar')))
                    )"""),
                ("Courses over-enrolled",
                 """SELECT c.id, c.title, c.students_per_lecture, COUNT(e.student_id) as enrolled
                    FROM courses c LEFT JOIN enrollment e ON c.id=e.course_id
                    GROUP BY c.id HAVING enrolled > c.students_per_lecture"""),
                ("Overlapping availability (teachers)",
                 """SELECT COUNT(*) FROM teacher_availability a1, teacher_availability a2
                    WHERE a1.entity_id=a2.entity_id AND a1.day=a2.day
                    AND a1.id<a2.id
                    AND a1.start_period<a2.end_period AND a1.end_period>a2.start_period"""),
                ("Preferred room type mismatch",
                 """SELECT COUNT(*) FROM teacher_assignments ta
                    JOIN courses c ON ta.course_id=c.id
                    JOIN rooms r ON ta.preferred_room_id=r.id
                    WHERE c.requires_lab=1 AND r.room_type NOT IN ('Laboratory','Computer Lab')
                       OR c.requires_lab=0 AND r.room_type IN ('Laboratory','Computer Lab')"""),
            ]
            
            for desc, query in checks:
                result = conn.execute(query).fetchone()
                count = result[0] if result else 0
                
                if count > 0:
                    self.logger.error(f"  ✗ {desc}: {count}")
                    valid = False
                else:
                    self.logger.info(f"  ✓ {desc}")
        
        if valid:
            self.logger.info("\n✓ All validation checks passed")
        
        return valid
    
    # ========================================================================
    # STATISTICS
    # ========================================================================
    
    def print_statistics(self) -> None:
        """Print comprehensive statistics."""
        self.logger.info("\n" + "="*60)
        self.logger.info("STATISTICS")
        self.logger.info("="*60)
        
        with db_manager.get_connection() as conn:
            for table in ['students', 'teachers', 'rooms', 'courses']:
                count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                self.logger.info(f"  {table.title()}: {count}")
            
            courses = conn.execute("SELECT COUNT(*) FROM courses").fetchone()[0]
            teachers = conn.execute("SELECT COUNT(*) FROM teachers").fetchone()[0]
            rooms = conn.execute("SELECT COUNT(*) FROM rooms").fetchone()[0]
            
            self.logger.info(f"\n  Resource Pressure:")
            self.logger.info(f"  Courses/Teacher: {courses/max(teachers,1):.1f}")
            self.logger.info(f"  Courses/Room: {courses/max(rooms,1):.1f}")
            
            self.logger.info(f"\n  Room Types:")
            for room_type in ['Lecture', 'Seminar', 'Laboratory', 'Computer Lab']:
                count = conn.execute(
                    "SELECT COUNT(*) FROM rooms WHERE room_type=?", (room_type,)
                ).fetchone()[0]
                self.logger.info(f"    {room_type}: {count}")
            
            student_avail = conn.execute(
                "SELECT COUNT(*) FROM student_availability").fetchone()[0]
            teacher_avail = conn.execute(
                "SELECT COUNT(*) FROM teacher_availability").fetchone()[0]
            
            self.logger.info(f"\n  Availability Records:")
            self.logger.info(f"  Student: {student_avail} "
                           f"(avg: {student_avail/max(len(self.students),1):.1f}/student)")
            self.logger.info(f"  Teacher: {teacher_avail} "
                           f"(avg: {teacher_avail/max(len(self.teachers),1):.1f}/teacher)")
            
            enrollments = conn.execute("SELECT COUNT(*) FROM enrollment").fetchone()[0]
            if self.students and self.courses:
                self.logger.info(f"\n  Enrollments: {enrollments}")
                self.logger.info(f"  Avg courses/student: {enrollments/len(self.students):.1f}")
                self.logger.info(f"  Avg students/course: {enrollments/len(self.courses):.1f}")
            
            workloads = conn.execute(
                "SELECT teacher_id, COUNT(*) as cnt FROM teacher_assignments GROUP BY teacher_id"
            ).fetchall()
            if workloads:
                counts = [w['cnt'] for w in workloads]
                self.logger.info(f"\n  Teacher Workload: avg={sum(counts)/len(counts):.1f}, "
                               f"min={min(counts)}, max={max(counts)}")
    
    # ========================================================================
    # UTILITIES
    # ========================================================================
    
    def _unique_name(self) -> str:
        for _ in range(100):
            name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
            if name not in self.used_names:
                self.used_names.add(name)
                return name
        counter = len(self.used_names) + 1
        while True:
            name = f"Person {counter}"
            if name not in self.used_names:
                self.used_names.add(name)
                return name
            counter += 1
    
    def _unique_email(self, name: str) -> str:
        parts = name.lower().split()
        base = f"{parts[0]}.{parts[-1]}@university.edu" if len(parts) > 1 else f"{parts[0]}@university.edu"
        
        if base not in self.used_emails:
            self.used_emails.add(base)
            return base
        
        for i in range(2, 1000):
            email = f"{parts[0]}.{parts[-1]}{i}@university.edu"
            if email not in self.used_emails:
                self.used_emails.add(email)
                return email
        
        counter = len(self.used_emails) + 1
        while True:
            email = f"user{counter}@university.edu"
            if email not in self.used_emails:
                self.used_emails.add(email)
                return email
            counter += 1
    
    def _batch_insert(self, table: str, columns: str, batch: List[Tuple]) -> None:
        if not batch:
            return
        with db_manager.get_connection() as conn:
            conn.executemany(f"INSERT INTO {table} {columns}", batch)
            conn.commit()
    
    def _load_students(self) -> None:
        with db_manager.get_connection() as conn:
            self.students = [dict(r) for r in conn.execute(
                "SELECT id, department, year_level FROM students ORDER BY id").fetchall()]
    
    def _load_teachers(self) -> None:
        with db_manager.get_connection() as conn:
            self.teachers = [dict(r) for r in conn.execute(
                "SELECT id, department FROM teachers ORDER BY id").fetchall()]
            for t in self.teachers:
                self.dept_teachers[t['department']].append(t['id'])
    
    def _load_rooms(self) -> None:
        with db_manager.get_connection() as conn:
            self.rooms = [dict(r) for r in conn.execute(
                "SELECT id, room_type, capacity, building FROM rooms ORDER BY id").fetchall()]
            for r in self.rooms:
                self.room_types[r['room_type']].append(r['id'])
                self.room_capacities[r['id']] = r['capacity']
                self.room_buildings[r['id']] = r['building']
    
    def _load_courses(self) -> None:
        with db_manager.get_connection() as conn:
            self.courses = [dict(r) for r in conn.execute(
                """SELECT id, title, department, requires_lab, students_per_lecture,
                   lectures_per_week, duration, year_level FROM courses ORDER BY id"""
            ).fetchall()]
            for c in self.courses:
                self.course_cache[c['id']] = c
    
    # ========================================================================
    # MAIN
    # ========================================================================
    
    def generate_all(self, clear: bool = False) -> None:
        """Generate all mock data."""
        start = datetime.now()
        random.seed(self.config.seed)
        
        try:
            if clear:
                self.clear_database()
            
            self.generate_students()
            self.generate_teachers()
            self.generate_rooms()
            self.generate_courses()
            self.assign_teachers()
            self.generate_enrollments()
            self.generate_availabilities()
            
            self.validate()
            self.print_statistics()
            
            elapsed = (datetime.now() - start).total_seconds()
            self.logger.info(f"\n✓ Generation complete in {elapsed:.1f}s")
            self.logger.info(f"  Difficulty: {self.config.difficulty}")
            self.logger.info(f"  Hint: Run with --difficulty hard for CP-SAT stress testing")
            
        except Exception as e:
            self.logger.error(f"Generation failed: {e}")
            import traceback
            traceback.print_exc()
            raise


# ============================================================================
# PUBLIC API
# ============================================================================

def generate_all_mock_data(
    student_count: int = 1000,
    teacher_count: int = 100,
    room_count: int = 60,
    course_count: int = 120,
    clear_first: bool = False,
    generate_schedule: bool = False,
    seed: int = 42,
    difficulty: str = "normal"
) -> None:
    """Public API for external imports."""
    config = GenerationConfig(
        student_count=student_count,
        teacher_count=teacher_count,
        room_count=room_count,
        course_count=course_count,
        seed=seed,
        difficulty=difficulty
    )
    MockDataGenerator(config).generate_all(clear=clear_first)


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Generate mock scheduling data for CP-SAT solver testing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python generate_mock_data.py --difficulty hard
  python generate_mock_data.py --students 2500 --rooms 50 --teachers 40 --difficulty hard
  python generate_mock_data.py --students 100 --difficulty easy
        """
    )
    parser.add_argument("--students", type=int, default=1000)
    parser.add_argument("--teachers", type=int, default=100)
    parser.add_argument("--rooms", type=int, default=60)
    parser.add_argument("--courses", type=int, default=120)
    parser.add_argument("--clear", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--difficulty", choices=["easy", "normal", "hard"], default="normal")
    parser.add_argument("--config", type=str)
    parser.add_argument("--db", type=str, default="scheduler.db")
    
    args = parser.parse_args()
    
    if args.config:
        with open(args.config) as f:
            config = GenerationConfig(**json.load(f))
    else:
        config = GenerationConfig(
            student_count=args.students,
            teacher_count=args.teachers,
            room_count=args.rooms,
            course_count=args.courses,
            seed=args.seed,
            difficulty=args.difficulty,
            db_path=args.db
        )
    
    try:
        MockDataGenerator(config).generate_all(clear=args.clear)
    except KeyboardInterrupt:
        print("\nInterrupted")
        sys.exit(0)

if __name__ == "__main__":
    main()
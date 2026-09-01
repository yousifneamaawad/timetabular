"""
Data models for the university scheduling system.
All entities are defined as dataclasses for type safety and clarity.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from enum import Enum, IntEnum


class RoomType(str, Enum):
    """Types of rooms available for scheduling."""
    LECTURE = "Lecture"
    LABORATORY = "Laboratory"
    COMPUTER_LAB = "Computer Lab"
    SEMINAR = "Seminar"


class Department(str, Enum):
    """Academic departments in the university."""
    COMPUTER_SCIENCE = "Computer Science"
    BUSINESS = "Business Administration"
    ENGINEERING = "Mechanical Engineering"
    ARTS = "Digital Arts"
    MATHEMATICS = "Mathematics"
    PHYSICS = "Physics"


class DayOfWeek(IntEnum):
    """Days of the week for scheduling."""
    MONDAY = 1
    TUESDAY = 2
    WEDNESDAY = 3
    THURSDAY = 4
    FRIDAY = 5
    SATURDAY = 6
    SUNDAY = 7


@dataclass
class Student:
    """Represents a university student."""
    id: int
    full_name: str
    department: Department
    year_level: int
    email: str
    
    def __post_init__(self):
        """Convert database strings to proper enum types."""
        if not isinstance(self.department, Department):
            self.department = Department(self.department)


@dataclass
class Teacher:
    """Represents a university teacher/instructor."""
    id: int
    full_name: str
    department: Department
    email: str
    
    def __post_init__(self):
        """Convert database strings to proper enum types."""
        if not isinstance(self.department, Department):
            self.department = Department(self.department)


@dataclass
class Room:
    """Represents a physical room or laboratory."""
    id: int
    room_name: str
    capacity: int
    room_type: RoomType
    building: str = "Main Building"
    floor: int = 1
    
    def __post_init__(self):
        """Convert database strings to proper enum types."""
        if not isinstance(self.room_type, RoomType):
            self.room_type = RoomType(self.room_type)
    
    @property
    def is_lab(self) -> bool:
        """Check if this room is a laboratory type."""
        return self.room_type in (RoomType.LABORATORY, RoomType.COMPUTER_LAB)


@dataclass
class Course:
    """Represents an academic course."""
    id: int
    title: str
    department: Department
    year_level: int
    lectures_per_week: int
    duration: int = 1
    students_per_lecture: int = 30
    requires_lab: bool = False
    
    def __post_init__(self):
        """Convert database strings to proper enum types."""
        if not isinstance(self.department, Department):
            self.department = Department(self.department)
    
    @property
    def total_lectures(self) -> int:
        """Total number of lecture instances per week."""
        return self.lectures_per_week


@dataclass
class Enrollment:
    """Links students to courses they are enrolled in."""
    student_id: int
    course_id: int


@dataclass
class TeacherAssignment:
    """Links teachers to courses they teach."""
    teacher_id: int
    course_id: int
    preferred_room_id: Optional[int] = None


@dataclass
class Availability:
    """Represents a time range when an entity is unavailable."""
    id: int  # Database primary key
    entity_id: int  # ID of the entity (student, teacher, or room)
    day: DayOfWeek
    start_period: int
    end_period: int
    
    def __post_init__(self):
        """Convert database strings to proper enum types."""
        if not isinstance(self.day, DayOfWeek):
            self.day = DayOfWeek(self.day)


@dataclass
class ScheduleEntry:
    """Represents a scheduled lecture in the timetable."""
    id: int  # Database primary key
    course_id: int
    lecture_number: int
    teacher_id: int
    room_id: int
    day: DayOfWeek
    start_period: int
    duration: int
    
    def __post_init__(self):
        """Convert database strings to proper enum types."""
        if not isinstance(self.day, DayOfWeek):
            self.day = DayOfWeek(self.day)
    
    @property
    def end_period(self) -> int:
        """Calculate the ending period of this entry."""
        return self.start_period + self.duration - 1


@dataclass
class SolverConfig:
    """Configuration parameters for the scheduling solver."""
    id: int = 1  # Database primary key
    slots_per_day: int = 8
    days_per_week: int = 5
    prevent_same_day: bool = True
    time_limit_seconds: float = 30.0
    last_solve_timestamp: Optional[datetime] = None
    best_objective_value: Optional[float] = None
    
    @property
    def total_slots(self) -> int:
        """Total number of time slots available."""
        return self.slots_per_day * self.days_per_week


@dataclass
class SolverWeights:
    """Weights for the multi-objective optimization function."""
    hard_constraint: int = 10000
    student_gaps: int = 80
    teacher_gaps: int = 100
    room_gaps: int = 60
    morning_preference: int = 20
    evening_penalty: int = 30
    preferred_room: int = 15
    balanced_schedule: int = 25
    consecutive_lectures: int = 10
    # Soft penalty per lecture that overlaps a student's stated unavailable
    # block. Deliberately much larger than the preference weights above
    # (student_gaps=80, teacher_gaps=100, ...) so the solver avoids
    # violations whenever any alternative exists, but small enough (vs.
    # a true hard constraint) that one unavoidable conflict doesn't make
    # the whole model INFEASIBLE. Teacher and room availability remain
    # hard constraints -- see constraints.py's _add_availability_constraints.
    student_availability_violation: int = 5000


@dataclass
class TimetableFilter:
    """Filter criteria for timetable display."""
    student_id: Optional[int] = None
    teacher_id: Optional[int] = None
    room_id: Optional[int] = None
    course_id: Optional[int] = None
    department: Optional[Department] = None
    year_level: Optional[int] = None
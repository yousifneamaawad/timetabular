# statistics.py
"""
Compute and analyze scheduling statistics and metrics.
"""

from dataclasses import dataclass
from collections import defaultdict
from typing import Optional

from database import db_manager


@dataclass
class ScheduleStatistics:
    """Container for all schedule statistics."""
    total_lectures: int
    total_courses: int
    total_teachers: int
    total_rooms: int
    room_utilization: dict[str, float]  # room_name -> utilization %
    teacher_workload: dict[str, int]    # teacher_name -> total periods
    average_student_gaps: float
    schedule_density: float
    unused_rooms: list[str]
    total_students: int
    
    def to_dict(self) -> dict:
        """Convert to dictionary for UI display."""
        return {
            'Total Lectures': self.total_lectures,
            'Total Courses': self.total_courses,
            'Total Teachers': self.total_teachers,
            'Total Rooms': self.total_rooms,
            'Average Student Gaps': f"{self.average_student_gaps:.2f}",
            'Schedule Density': f"{self.schedule_density:.1%}",
            'Unused Rooms': len(self.unused_rooms),
            'Total Students': self.total_students,
        }


class StatisticsCalculator:
    """Calculate various statistics from the schedule database."""
    
    def __init__(self):
        self.config = None
        self._load_config()
    
    def _load_config(self):
        """Load solver configuration for calculations."""
        with db_manager.get_connection() as conn:
            row = conn.execute("SELECT * FROM solver_config WHERE id = 1").fetchone()
            if row:
                self.config = dict(row)
    
    def compute_all(self) -> ScheduleStatistics:
        """Compute all available statistics."""
        with db_manager.get_connection() as conn:
            # Basic counts
            total_lectures = conn.execute(
                "SELECT COUNT(*) FROM schedule"
            ).fetchone()[0]
            
            total_courses = conn.execute(
                "SELECT COUNT(DISTINCT course_id) FROM schedule"
            ).fetchone()[0]
            
            total_teachers = conn.execute(
                "SELECT COUNT(DISTINCT teacher_id) FROM schedule"
            ).fetchone()[0]
            
            total_rooms = conn.execute(
                "SELECT COUNT(DISTINCT room_id) FROM schedule"
            ).fetchone()[0]
            
            total_students = conn.execute(
                "SELECT COUNT(*) FROM students"
            ).fetchone()[0]
            
            # Room utilization
            room_util = self._calculate_room_utilization(conn)
            
            # Teacher workload
            teacher_workload = self._calculate_teacher_workload(conn)
            
            # Student gaps
            avg_gaps = self._calculate_average_student_gaps(conn)
            
            # Schedule density
            density = self._calculate_schedule_density(conn, total_lectures)
            
            # Unused rooms
            unused = self._find_unused_rooms(conn)
        
        return ScheduleStatistics(
            total_lectures=total_lectures,
            total_courses=total_courses,
            total_teachers=total_teachers,
            total_rooms=total_rooms,
            room_utilization=room_util,
            teacher_workload=teacher_workload,
            average_student_gaps=avg_gaps,
            schedule_density=density,
            unused_rooms=unused,
            total_students=total_students,
        )
    
    def _calculate_room_utilization(self, conn) -> dict[str, float]:
        """Calculate utilization percentage for each room."""
        rooms = conn.execute("SELECT id, room_name FROM rooms").fetchall()
        total_slots = (self.config['slots_per_day'] * self.config['days_per_week'] 
                      if self.config else 40)
        
        utilization = {}
        for room_id, room_name in rooms:
            used_slots = conn.execute(
                "SELECT SUM(duration) FROM schedule WHERE room_id = ?",
                (room_id,)
            ).fetchone()[0] or 0
            utilization[room_name] = (used_slots / total_slots) * 100
        
        return utilization
    
    def _calculate_teacher_workload(self, conn) -> dict[str, int]:
        """Calculate total teaching periods per teacher."""
        teachers = conn.execute(
            """SELECT DISTINCT t.id, t.full_name 
               FROM teachers t 
               JOIN schedule s ON t.id = s.teacher_id"""
        ).fetchall()
        
        workload = {}
        for teacher_id, name in teachers:
            total_periods = conn.execute(
                "SELECT SUM(duration) FROM schedule WHERE teacher_id = ?",
                (teacher_id,)
            ).fetchone()[0] or 0
            workload[name] = total_periods
        
        return workload
    
    def _calculate_average_student_gaps(self, conn) -> float:
        """Calculate average number of gaps per student per day."""
        students = conn.execute("SELECT id FROM students").fetchall()
        total_gaps = 0
        student_count = len(students)
        
        if student_count == 0:
            return 0.0
        
        for (student_id,) in students:
            # Get all lectures for this student
            lectures = conn.execute(
                """SELECT s.day, s.start_period, s.duration 
                   FROM schedule s
                   JOIN enrollment e ON s.course_id = e.course_id
                   WHERE e.student_id = ?
                   ORDER BY s.day, s.start_period""",
                (student_id,)
            ).fetchall()
            
            if not lectures:
                continue
            
            # Group by day
            by_day = defaultdict(list)
            for day, start, duration in lectures:
                by_day[day].append((start, start + duration))
            
            # Calculate gaps for each day
            for day_lectures in by_day.values():
                day_lectures.sort()
                for i in range(len(day_lectures) - 1):
                    gap = day_lectures[i + 1][0] - day_lectures[i][1]
                    if gap > 0:
                        total_gaps += gap
        
        return total_gaps / (student_count * (self.config['days_per_week'] or 5))
    
    def _calculate_schedule_density(self, conn, total_lectures: int) -> float:
        """Calculate how densely the schedule is packed."""
        if not self.config:
            return 0.0
        
        total_slots = (self.config['slots_per_day'] * 
                      self.config['days_per_week'] * 
                      self._get_total_rooms(conn))
        
        if total_slots == 0:
            return 0.0
        
        return total_lectures / total_slots
    
    def _get_total_rooms(self, conn) -> int:
        """Get total number of rooms."""
        return conn.execute("SELECT COUNT(*) FROM rooms").fetchone()[0]
    
    def _find_unused_rooms(self, conn) -> list[str]:
        """Find rooms that are not used in the schedule."""
        used_rooms = set(
            row[0] for row in conn.execute(
                "SELECT DISTINCT room_id FROM schedule"
            ).fetchall()
        )
        
        all_rooms = conn.execute("SELECT id, room_name FROM rooms").fetchall()
        return [name for room_id, name in all_rooms if room_id not in used_rooms]
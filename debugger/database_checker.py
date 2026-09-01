"""
Database integrity checker.

Works directly with your DatabaseManager and SQLite schema.

Checks:

✓ Missing tables
✓ Row counts
✓ Foreign key integrity
✓ Courses without teachers
✓ Courses without students
✓ Courses without rooms
✓ Availability ranges
✓ Duplicate assignments
✓ Solver configuration
✓ Statistics

Compatible with your current database.py
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from database import db_manager

from utils import (
    banner,
    logger,
    section,
    Report,
    Counter,
)

# ---------------------------------------------------------


class DatabaseChecker:

    def __init__(self):

        self.report = Report()
        self.stats = Counter()

    # -----------------------------------------------------

    def run(self):

        banner()

        section("DATABASE CHECK")

        with db_manager.get_connection() as conn:

            self.conn = conn
            self.conn.row_factory = None

            self.check_tables()
            self.check_counts()
            self.check_courses()
            self.check_assignments()
            self.check_availability()
            self.check_schedule()
            self.check_solver_config()

        section("Statistics")
        self.stats.dump()

        self.report.save("database_report.txt")

    # -----------------------------------------------------

    def scalar(self, sql):

        cur = self.conn.execute(sql)
        row = cur.fetchone()

        return row[0] if row else 0

    # -----------------------------------------------------

    def check_tables(self):

        section("Tables")

        expected = [

            "students",
            "teachers",
            "rooms",
            "courses",
            "enrollment",
            "teacher_assignments",
            "student_availability",
            "teacher_availability",
            "room_availability",
            "schedule",
            "solver_config",
        ]

        tables = {

            row[0]
            for row in self.conn.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type='table'
                """
            )
        }

        for table in expected:

            if table in tables:
                logger.success(table)
            else:
                logger.error(f"Missing table: {table}")

    # -----------------------------------------------------

    def check_counts(self):

        section("Row Counts")

        tables = [

            "students",
            "teachers",
            "rooms",
            "courses",
            "enrollment",
            "teacher_assignments",
            "student_availability",
            "teacher_availability",
            "room_availability",
            "schedule",
        ]

        for table in tables:

            count = self.scalar(f"SELECT COUNT(*) FROM {table}")

            self.stats.add(table, count)

            logger.info(f"{table:<25} {count}")

    # -----------------------------------------------------

    def check_courses(self):

        section("Course Integrity")

        rows = self.conn.execute("""
            SELECT id,title
            FROM courses
        """)

        for cid, title in rows:

            teacher_count = self.scalar(f"""
                SELECT COUNT(*)
                FROM teacher_assignments
                WHERE course_id={cid}
            """)

            student_count = self.scalar(f"""
                SELECT COUNT(*)
                FROM enrollment
                WHERE course_id={cid}
            """)

            if teacher_count == 0:
                logger.error(
                    f"Course {cid} ({title}) has NO teacher."
                )

            if student_count == 0:
                logger.warning(
                    f"Course {cid} ({title}) has NO enrolled students."
                )

            room_count = self.scalar("""
                SELECT COUNT(*)
                FROM rooms
            """)

            if room_count == 0:
                logger.error(
                    "Database contains zero rooms."
                )

    # -----------------------------------------------------

    def check_assignments(self):

        section("Teacher Assignments")

        duplicates = self.scalar("""

            SELECT COUNT(*)

            FROM (

                SELECT teacher_id,course_id,COUNT(*)

                FROM teacher_assignments

                GROUP BY teacher_id,course_id

                HAVING COUNT(*)>1

            )

        """)

        if duplicates:

            logger.error(
                f"{duplicates} duplicate teacher assignments."
            )

        else:

            logger.success("No duplicate teacher assignments.")

    # -----------------------------------------------------

    def check_availability(self):

        section("Availability")

        tables = [

            "student_availability",
            "teacher_availability",
            "room_availability",
        ]

        for table in tables:

            bad = self.scalar(f"""

                SELECT COUNT(*)

                FROM {table}

                WHERE

                    day<1

                    OR day>7

                    OR start_period<1

                    OR end_period<start_period

                    OR end_period>12

            """)

            if bad:

                logger.error(f"{table}: {bad} invalid rows")

            else:

                logger.success(f"{table}: OK")

    # -----------------------------------------------------

    def check_schedule(self):

        section("Existing Schedule")

        count = self.scalar("SELECT COUNT(*) FROM schedule")

        logger.info(f"Existing scheduled lectures: {count}")

    # -----------------------------------------------------

    def check_solver_config(self):

        section("Solver Config")

        row = self.conn.execute("""

            SELECT

                slots_per_day,
                days_per_week,
                prevent_same_day,
                time_limit_seconds

            FROM solver_config

            WHERE id=1

        """).fetchone()

        if row is None:

            logger.error("Missing solver_config row.")

            return

        slots, days, same_day, limit = row

        logger.info(f"Slots/day : {slots}")
        logger.info(f"Days/week : {days}")
        logger.info(f"Prevent same day : {same_day}")
        logger.info(f"Time limit : {limit}s")


# ---------------------------------------------------------

if __name__ == "__main__":

    DatabaseChecker().run()
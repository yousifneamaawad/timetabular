"""
Database initialization and connection management for the university scheduling system.
Handles schema creation, connection pooling, and safe concurrent access.
"""

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional
import logging
from models import SolverConfig
logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    Thread-safe SQLite connection manager with WAL mode support.
    Handles concurrent read/write access for UI and solver threads.
    """
    
    def __init__(self, db_path: str = "scheduler.db", max_connections: int = 5):
        self.db_path = Path(db_path)
        self.max_connections = max_connections
        self._connections: list[sqlite3.Connection] = []
        self._lock = threading.Lock()
        self._init_database()
    
    def _init_database(self) -> None:
        """Create database schema if it doesn't exist and run migrations."""
        with self.get_connection() as conn:
            # Enable WAL mode as a database property (only needs to be set once)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            
            conn.executescript(SCHEMA_SQL)
            conn.commit()
            
            # Run schema updates after initial schema creation
            self._update_schema(conn)
            conn.commit()
            
        logger.info(f"Database initialized at {self.db_path}")
    
    def _update_schema(self, conn: sqlite3.Connection) -> None:
        """Check and update database schema if needed."""
        cursor = conn.cursor()
        
        # Check rooms table columns
        cursor.execute("PRAGMA table_info(rooms)")
        columns = [col[1] for col in cursor.fetchall()]
        
        updates = []
        if 'building' not in columns:
            updates.append("ALTER TABLE rooms ADD COLUMN building TEXT NOT NULL DEFAULT 'Main Building'")
        if 'floor' not in columns:
            updates.append("ALTER TABLE rooms ADD COLUMN floor INTEGER NOT NULL DEFAULT 1")
        if 'room_type' not in columns:
            updates.append("ALTER TABLE rooms ADD COLUMN room_type TEXT NOT NULL DEFAULT 'Lecture'")
        
        # Apply updates
        for update in updates:
            try:
                cursor.execute(update)
                logger.info(f"Applied schema update: {update}")
            except Exception as e:
                logger.warning(f"Could not apply update '{update}': {e}")
        
        # Create missing indexes
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_teacher_assignments_teacher ON teacher_assignments(teacher_id)",
            "CREATE INDEX IF NOT EXISTS idx_teacher_assignments_course ON teacher_assignments(course_id)",
            "CREATE INDEX IF NOT EXISTS idx_student_department ON students(department)",
            "CREATE INDEX IF NOT EXISTS idx_course_department ON courses(department)",
            "CREATE INDEX IF NOT EXISTS idx_enrollment_student ON enrollment(student_id)",
            "CREATE INDEX IF NOT EXISTS idx_enrollment_course ON enrollment(course_id)",
            "CREATE INDEX IF NOT EXISTS idx_schedule_course ON schedule(course_id)",
            "CREATE INDEX IF NOT EXISTS idx_schedule_teacher ON schedule(teacher_id)",
            "CREATE INDEX IF NOT EXISTS idx_schedule_room ON schedule(room_id)",
            "CREATE INDEX IF NOT EXISTS idx_schedule_day_period ON schedule(day, start_period)",
            "CREATE INDEX IF NOT EXISTS idx_student_availability_entity ON student_availability(entity_id)",
            "CREATE INDEX IF NOT EXISTS idx_teacher_availability_entity ON teacher_availability(entity_id)",
            "CREATE INDEX IF NOT EXISTS idx_room_availability_entity ON room_availability(entity_id)",
        ]
        
        for index_sql in indexes:
            try:
                cursor.execute(index_sql)
            except Exception as e:
                logger.warning(f"Could not create index: {e}")
    
    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """
        Get a database connection from the pool.
        Automatically handles connection lifecycle and WAL mode.
        """
        conn = None
        with self._lock:
            if self._connections:
                conn = self._connections.pop()
            else:
                conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA foreign_keys=ON")
                conn.row_factory = sqlite3.Row
        
        try:
            yield conn
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            with self._lock:
                if len(self._connections) < self.max_connections:
                    self._connections.append(conn)
                else:
                    conn.close()


    def load_solver_config(self) -> SolverConfig:
        with self.get_connection() as conn:

            row = conn.execute("""
                SELECT *
                FROM solver_config
                WHERE id = 1
            """).fetchone()

            if row is None:

                config = SolverConfig()

                conn.execute("""
                    INSERT INTO solver_config (
                        id,
                        slots_per_day,
                        days_per_week,
                        prevent_same_day,
                        time_limit_seconds,
                        last_solve_timestamp,
                        best_objective_value
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    config.id,
                    config.slots_per_day,
                    config.days_per_week,
                    int(config.prevent_same_day),
                    config.time_limit_seconds,
                    config.last_solve_timestamp,
                    config.best_objective_value,
                ))

                conn.commit()

                return config

            return SolverConfig(
                id=row["id"],
                slots_per_day=row["slots_per_day"],
                days_per_week=row["days_per_week"],
                prevent_same_day=bool(row["prevent_same_day"]),
                time_limit_seconds=row["time_limit_seconds"],
                last_solve_timestamp=row["last_solve_timestamp"],
                best_objective_value=row["best_objective_value"],
            )








    def save_solver_config(self, config: SolverConfig) -> None:
        """
        Save the solver configuration to the database.
        """
        with self.get_connection() as conn:
            conn.execute("""
                UPDATE solver_config
                SET
                    slots_per_day = ?,
                    days_per_week = ?,
                    prevent_same_day = ?,
                    time_limit_seconds = ?,
                    last_solve_timestamp = ?,
                    best_objective_value = ?
                WHERE id = ?
            """, (
                config.slots_per_day,
                config.days_per_week,
                int(config.prevent_same_day),
                config.time_limit_seconds,
                config.last_solve_timestamp,
                config.best_objective_value,
                config.id,
            ))

            conn.commit()










    def close_all(self) -> None:
        """Close all connections in the pool."""
        with self._lock:
            for conn in self._connections:
                conn.close()
            self._connections.clear()


SCHEMA_SQL = """
-- Students table
CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    department TEXT NOT NULL,
    year_level INTEGER NOT NULL CHECK (year_level BETWEEN 1 AND 5),
    email TEXT UNIQUE NOT NULL
);

-- Teachers table
CREATE TABLE IF NOT EXISTS teachers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    department TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL
);

-- Rooms table
CREATE TABLE IF NOT EXISTS rooms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_name TEXT UNIQUE NOT NULL,
    capacity INTEGER NOT NULL CHECK (capacity > 0),
    room_type TEXT NOT NULL CHECK (room_type IN ('Lecture', 'Laboratory', 'Computer Lab', 'Seminar')),
    building TEXT NOT NULL DEFAULT 'Main Building',
    floor INTEGER NOT NULL DEFAULT 1
);

-- Courses table
CREATE TABLE IF NOT EXISTS courses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    department TEXT NOT NULL,
    year_level INTEGER NOT NULL CHECK (year_level BETWEEN 1 AND 5),
    lectures_per_week INTEGER NOT NULL CHECK (lectures_per_week > 0),
    duration INTEGER NOT NULL DEFAULT 1 CHECK (duration > 0),
    students_per_lecture INTEGER NOT NULL CHECK (students_per_lecture > 0),
    requires_lab BOOLEAN NOT NULL DEFAULT 0
);

-- Enrollment (many-to-many: students <-> courses)
CREATE TABLE IF NOT EXISTS enrollment (
    student_id INTEGER NOT NULL,
    course_id INTEGER NOT NULL,
    PRIMARY KEY (student_id, course_id),
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE
);

-- Teacher assignments (many-to-many: teachers <-> courses)
CREATE TABLE IF NOT EXISTS teacher_assignments (
    teacher_id INTEGER NOT NULL,
    course_id INTEGER NOT NULL,
    preferred_room_id INTEGER,
    PRIMARY KEY (teacher_id, course_id),
    FOREIGN KEY (teacher_id) REFERENCES teachers(id) ON DELETE CASCADE,
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
    FOREIGN KEY (preferred_room_id) REFERENCES rooms(id) ON DELETE SET NULL
);

-- Student availability
CREATE TABLE IF NOT EXISTS student_availability (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id INTEGER NOT NULL,
    day INTEGER NOT NULL CHECK (day BETWEEN 1 AND 7),
    start_period INTEGER NOT NULL CHECK (start_period BETWEEN 1 AND 12),
    end_period INTEGER NOT NULL CHECK (end_period >= start_period AND end_period <= 12),
    FOREIGN KEY (entity_id) REFERENCES students(id) ON DELETE CASCADE
);

-- Teacher availability
CREATE TABLE IF NOT EXISTS teacher_availability (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id INTEGER NOT NULL,
    day INTEGER NOT NULL CHECK (day BETWEEN 1 AND 7),
    start_period INTEGER NOT NULL CHECK (start_period BETWEEN 1 AND 12),
    end_period INTEGER NOT NULL CHECK (end_period >= start_period AND end_period <= 12),
    FOREIGN KEY (entity_id) REFERENCES teachers(id) ON DELETE CASCADE
);

-- Room availability
CREATE TABLE IF NOT EXISTS room_availability (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id INTEGER NOT NULL,
    day INTEGER NOT NULL CHECK (day BETWEEN 1 AND 7),
    start_period INTEGER NOT NULL CHECK (start_period BETWEEN 1 AND 12),
    end_period INTEGER NOT NULL CHECK (end_period >= start_period AND end_period <= 12),
    FOREIGN KEY (entity_id) REFERENCES rooms(id) ON DELETE CASCADE
);

-- Schedule output table
CREATE TABLE IF NOT EXISTS schedule (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER NOT NULL,
    lecture_number INTEGER NOT NULL,
    teacher_id INTEGER NOT NULL,
    room_id INTEGER NOT NULL,
    day INTEGER NOT NULL CHECK (day BETWEEN 1 AND 7),
    start_period INTEGER NOT NULL CHECK (start_period BETWEEN 1 AND 12),
    duration INTEGER NOT NULL CHECK (duration > 0),
    UNIQUE(course_id, lecture_number),
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
    FOREIGN KEY (teacher_id) REFERENCES teachers(id) ON DELETE CASCADE,
    FOREIGN KEY (room_id) REFERENCES rooms(id) ON DELETE CASCADE
);

-- Solver configuration storage
CREATE TABLE IF NOT EXISTS solver_config (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    slots_per_day INTEGER NOT NULL DEFAULT 8,
    days_per_week INTEGER NOT NULL DEFAULT 5,
    prevent_same_day BOOLEAN NOT NULL DEFAULT 1,
    time_limit_seconds REAL NOT NULL DEFAULT 30.0,
    last_solve_timestamp TEXT,
    best_objective_value REAL
);

-- Insert default configuration if not exists
INSERT OR IGNORE INTO solver_config (id) VALUES (1);
"""


# Global database instance
db_manager = DatabaseManager()


if __name__ == "__main__":
    db_manager._init_database()
    print("Database initialized successfully!")
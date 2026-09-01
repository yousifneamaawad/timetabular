#!/usr/bin/env python3
"""
University Scheduling Database Editor
A CustomTkinter GUI for managing all entities used by the CP-SAT solver.
"""

import customtkinter as ctk
from tkinter import messagebox, ttk
from typing import List, Dict, Any
import sys
from pathlib import Path

# Add the parent directory to sys.path so we can import database
sys.path.insert(0, str(Path(__file__).parent))
from database import db_manager
from generate_mock_data import generate_all_mock_data

# ----------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------
DEPARTMENTS = [
    "Computer Science",
    "Business Administration",
    "Mechanical Engineering",
    "Digital Arts",
    "Mathematics",
    "Physics",
]
ROOM_TYPES = ["Lecture", "Laboratory", "Computer Lab", "Seminar"]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# ----------------------------------------------------------------------
# Helper: refresh Treeview with data
# ----------------------------------------------------------------------
def refresh_treeview(tree: ttk.Treeview, query: str, columns: tuple, headings: tuple = None):
    """Clear the treeview and fill it with the result of the SQL query."""
    tree.delete(*tree.get_children())
    with db_manager.get_connection() as conn:
        rows = conn.execute(query).fetchall()
    for row in rows:
        values = tuple(row[col] for col in columns)
        tree.insert("", "end", values=values)

# ----------------------------------------------------------------------
# Main Application Class
# ----------------------------------------------------------------------
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("University Scheduling Database Editor")
        self.geometry("1200x800")
        ctk.set_appearance_mode("System")  # "Dark" or "Light"
        ctk.set_default_color_theme("blue")

        # Tab view
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=10, pady=10)

        # Add tabs
        self.tabs = {}
        for name in ["Students", "Teachers", "Rooms", "Courses",
                     "Enrollments", "Teacher Assignments",
                     "Student Availability", "Teacher Availability",
                     "Room Availability", "Solver Config", "Mock Data"]:
            self.tabs[name] = self.tabview.add(name)

        # Build each tab
        self._build_students_tab()
        self._build_teachers_tab()
        self._build_rooms_tab()
        self._build_courses_tab()
        self._build_enrollments_tab()
        self._build_teacher_assignments_tab()
        self._build_student_availability_tab()
        self._build_teacher_availability_tab()
        self._build_room_availability_tab()
        self._build_solver_config_tab()
        self._build_mock_data_tab()

    # ------------------------------------------------------------------
    # Students Tab
    # ------------------------------------------------------------------
    def _build_students_tab(self):
        tab = self.tabs["Students"]
        frame = ctk.CTkFrame(tab)
        frame.pack(fill="both", expand=True, padx=5, pady=5)

        # Treeview
        columns = ("id", "full_name", "department", "year_level", "email")
        tree = ttk.Treeview(frame, columns=columns, show="headings")
        for col in columns:
            tree.heading(col, text=col.replace("_", " ").title())
        tree.pack(fill="both", expand=True, side="left")

        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        scrollbar.pack(side="right", fill="y")
        tree.configure(yscrollcommand=scrollbar.set)

        # Input fields
        input_frame = ctk.CTkFrame(tab)
        input_frame.pack(fill="x", padx=5, pady=5)

        ctk.CTkLabel(input_frame, text="Full Name:").grid(row=0, column=0, padx=2, pady=2, sticky="e")
        self.student_name = ctk.CTkEntry(input_frame, width=150)
        self.student_name.grid(row=0, column=1, padx=2, pady=2)

        ctk.CTkLabel(input_frame, text="Department:").grid(row=0, column=2, padx=2, pady=2, sticky="e")
        self.student_dept = ctk.CTkComboBox(input_frame, values=DEPARTMENTS, width=150)
        self.student_dept.grid(row=0, column=3, padx=2, pady=2)

        ctk.CTkLabel(input_frame, text="Year (1-5):").grid(row=0, column=4, padx=2, pady=2, sticky="e")
        self.student_year = ctk.CTkEntry(input_frame, width=50)
        self.student_year.grid(row=0, column=5, padx=2, pady=2)

        ctk.CTkLabel(input_frame, text="Email:").grid(row=0, column=6, padx=2, pady=2, sticky="e")
        self.student_email = ctk.CTkEntry(input_frame, width=150)
        self.student_email.grid(row=0, column=7, padx=2, pady=2)

        # Buttons
        btn_frame = ctk.CTkFrame(tab)
        btn_frame.pack(fill="x", padx=5, pady=5)

        def add_student():
            try:
                name = self.student_name.get()
                dept = self.student_dept.get()
                year = int(self.student_year.get())
                email = self.student_email.get()
                if not name or not dept or not email:
                    raise ValueError("All fields are required.")
                if year < 1 or year > 5:
                    raise ValueError("Year must be between 1 and 5.")
                with db_manager.get_connection() as conn:
                    conn.execute(
                        "INSERT INTO students (full_name, department, year_level, email) VALUES (?,?,?,?)",
                        (name, dept, year, email)
                    )
                refresh_treeview(tree, "SELECT * FROM students", columns)
                messagebox.showinfo("Success", "Student added.")
            except Exception as e:
                messagebox.showerror("Error", str(e))

        def delete_student():
            selected = tree.selection()
            if not selected:
                messagebox.showwarning("No selection", "Select a student first.")
                return
            item = tree.item(selected[0])['values']
            student_id = item[0]
            if messagebox.askyesno("Confirm", f"Delete student {item[1]}?"):
                with db_manager.get_connection() as conn:
                    conn.execute("DELETE FROM students WHERE id=?", (student_id,))
                refresh_treeview(tree, "SELECT * FROM students", columns)

        ctk.CTkButton(btn_frame, text="Add", command=add_student).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="Delete", command=delete_student).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="Refresh", command=lambda: refresh_treeview(tree, "SELECT * FROM students", columns)).pack(side="left", padx=5)

        # Initial load
        refresh_treeview(tree, "SELECT * FROM students", columns)

    # ------------------------------------------------------------------
    # Teachers Tab (similar pattern)
    # ------------------------------------------------------------------
    def _build_teachers_tab(self):
        tab = self.tabs["Teachers"]
        frame = ctk.CTkFrame(tab)
        frame.pack(fill="both", expand=True, padx=5, pady=5)

        columns = ("id", "full_name", "department", "email")
        tree = ttk.Treeview(frame, columns=columns, show="headings")
        for col in columns:
            tree.heading(col, text=col.replace("_", " ").title())
        tree.pack(fill="both", expand=True, side="left")

        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        scrollbar.pack(side="right", fill="y")
        tree.configure(yscrollcommand=scrollbar.set)

        input_frame = ctk.CTkFrame(tab)
        input_frame.pack(fill="x", padx=5, pady=5)

        ctk.CTkLabel(input_frame, text="Full Name:").grid(row=0, column=0, padx=2, pady=2, sticky="e")
        self.teacher_name = ctk.CTkEntry(input_frame, width=150)
        self.teacher_name.grid(row=0, column=1, padx=2, pady=2)

        ctk.CTkLabel(input_frame, text="Department:").grid(row=0, column=2, padx=2, pady=2, sticky="e")
        self.teacher_dept = ctk.CTkComboBox(input_frame, values=DEPARTMENTS, width=150)
        self.teacher_dept.grid(row=0, column=3, padx=2, pady=2)

        ctk.CTkLabel(input_frame, text="Email:").grid(row=0, column=4, padx=2, pady=2, sticky="e")
        self.teacher_email = ctk.CTkEntry(input_frame, width=150)
        self.teacher_email.grid(row=0, column=5, padx=2, pady=2)

        btn_frame = ctk.CTkFrame(tab)
        btn_frame.pack(fill="x", padx=5, pady=5)

        def add_teacher():
            try:
                name = self.teacher_name.get()
                dept = self.teacher_dept.get()
                email = self.teacher_email.get()
                if not name or not dept or not email:
                    raise ValueError("All fields required.")
                with db_manager.get_connection() as conn:
                    conn.execute(
                        "INSERT INTO teachers (full_name, department, email) VALUES (?,?,?)",
                        (name, dept, email))
                refresh_treeview(tree, "SELECT * FROM teachers", columns)
                messagebox.showinfo("Success", "Teacher added.")
            except Exception as e:
                messagebox.showerror("Error", str(e))

        def delete_teacher():
            selected = tree.selection()
            if not selected:
                return
            item = tree.item(selected[0])['values']
            tid = item[0]
            if messagebox.askyesno("Confirm", f"Delete teacher {item[1]}?"):
                with db_manager.get_connection() as conn:
                    conn.execute("DELETE FROM teachers WHERE id=?", (tid,))
                refresh_treeview(tree, "SELECT * FROM teachers", columns)

        ctk.CTkButton(btn_frame, text="Add", command=add_teacher).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="Delete", command=delete_teacher).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="Refresh", command=lambda: refresh_treeview(tree, "SELECT * FROM teachers", columns)).pack(side="left", padx=5)

        refresh_treeview(tree, "SELECT * FROM teachers", columns)

    # ------------------------------------------------------------------
    # Rooms Tab
    # ------------------------------------------------------------------
    def _build_rooms_tab(self):
        tab = self.tabs["Rooms"]
        frame = ctk.CTkFrame(tab)
        frame.pack(fill="both", expand=True, padx=5, pady=5)

        columns = ("id", "room_name", "capacity", "room_type", "building", "floor")
        tree = ttk.Treeview(frame, columns=columns, show="headings")
        for col in columns:
            tree.heading(col, text=col.replace("_", " ").title())
        tree.pack(fill="both", expand=True, side="left")

        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        scrollbar.pack(side="right", fill="y")
        tree.configure(yscrollcommand=scrollbar.set)

        input_frame = ctk.CTkFrame(tab)
        input_frame.pack(fill="x", padx=5, pady=5)

        ctk.CTkLabel(input_frame, text="Room Name:").grid(row=0, column=0, padx=2, pady=2, sticky="e")
        self.room_name = ctk.CTkEntry(input_frame, width=100)
        self.room_name.grid(row=0, column=1, padx=2, pady=2)

        ctk.CTkLabel(input_frame, text="Capacity:").grid(row=0, column=2, padx=2, pady=2, sticky="e")
        self.room_capacity = ctk.CTkEntry(input_frame, width=60)
        self.room_capacity.grid(row=0, column=3, padx=2, pady=2)

        ctk.CTkLabel(input_frame, text="Type:").grid(row=0, column=4, padx=2, pady=2, sticky="e")
        self.room_type = ctk.CTkComboBox(input_frame, values=ROOM_TYPES, width=120)
        self.room_type.grid(row=0, column=5, padx=2, pady=2)

        ctk.CTkLabel(input_frame, text="Building:").grid(row=0, column=6, padx=2, pady=2, sticky="e")
        self.room_building = ctk.CTkEntry(input_frame, width=120)
        self.room_building.grid(row=0, column=7, padx=2, pady=2)

        ctk.CTkLabel(input_frame, text="Floor:").grid(row=0, column=8, padx=2, pady=2, sticky="e")
        self.room_floor = ctk.CTkEntry(input_frame, width=50)
        self.room_floor.grid(row=0, column=9, padx=2, pady=2)

        btn_frame = ctk.CTkFrame(tab)
        btn_frame.pack(fill="x", padx=5, pady=5)

        def add_room():
            try:
                name = self.room_name.get()
                cap = int(self.room_capacity.get())
                rtype = self.room_type.get()
                building = self.room_building.get()
                floor = int(self.room_floor.get())
                if cap <= 0 or floor < 1:
                    raise ValueError("Capacity >0, floor >=1")
                with db_manager.get_connection() as conn:
                    conn.execute(
                        "INSERT INTO rooms (room_name, capacity, room_type, building, floor) VALUES (?,?,?,?,?)",
                        (name, cap, rtype, building, floor))
                refresh_treeview(tree, "SELECT * FROM rooms", columns)
                messagebox.showinfo("Success", "Room added.")
            except Exception as e:
                messagebox.showerror("Error", str(e))

        def delete_room():
            selected = tree.selection()
            if not selected:
                return
            item = tree.item(selected[0])['values']
            rid = item[0]
            if messagebox.askyesno("Confirm", f"Delete room {item[1]}?"):
                with db_manager.get_connection() as conn:
                    conn.execute("DELETE FROM rooms WHERE id=?", (rid,))
                refresh_treeview(tree, "SELECT * FROM rooms", columns)

        ctk.CTkButton(btn_frame, text="Add", command=add_room).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="Delete", command=delete_room).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="Refresh", command=lambda: refresh_treeview(tree, "SELECT * FROM rooms", columns)).pack(side="left", padx=5)

        refresh_treeview(tree, "SELECT * FROM rooms", columns)

    # ------------------------------------------------------------------
    # Courses Tab
    # ------------------------------------------------------------------
    def _build_courses_tab(self):
        tab = self.tabs["Courses"]
        frame = ctk.CTkFrame(tab)
        frame.pack(fill="both", expand=True, padx=5, pady=5)

        columns = ("id", "title", "department", "year_level", "lectures_per_week",
                   "duration", "students_per_lecture", "requires_lab")
        tree = ttk.Treeview(frame, columns=columns, show="headings")
        for col in columns:
            tree.heading(col, text=col.replace("_", " ").title())
        tree.pack(fill="both", expand=True, side="left")

        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        scrollbar.pack(side="right", fill="y")
        tree.configure(yscrollcommand=scrollbar.set)

        input_frame = ctk.CTkFrame(tab)
        input_frame.pack(fill="x", padx=5, pady=5)

        row = 0
        ctk.CTkLabel(input_frame, text="Title:").grid(row=row, column=0, padx=2, pady=2, sticky="e")
        self.course_title = ctk.CTkEntry(input_frame, width=150)
        self.course_title.grid(row=row, column=1, padx=2, pady=2)

        ctk.CTkLabel(input_frame, text="Department:").grid(row=row, column=2, padx=2, pady=2, sticky="e")
        self.course_dept = ctk.CTkComboBox(input_frame, values=DEPARTMENTS, width=150)
        self.course_dept.grid(row=row, column=3, padx=2, pady=2)

        ctk.CTkLabel(input_frame, text="Year:").grid(row=row, column=4, padx=2, pady=2, sticky="e")
        self.course_year = ctk.CTkEntry(input_frame, width=50)
        self.course_year.grid(row=row, column=5, padx=2, pady=2)

        row += 1
        ctk.CTkLabel(input_frame, text="Lectures/Week:").grid(row=row, column=0, padx=2, pady=2, sticky="e")
        self.course_lectures = ctk.CTkEntry(input_frame, width=50)
        self.course_lectures.grid(row=row, column=1, padx=2, pady=2)

        ctk.CTkLabel(input_frame, text="Duration:").grid(row=row, column=2, padx=2, pady=2, sticky="e")
        self.course_duration = ctk.CTkEntry(input_frame, width=50)
        self.course_duration.grid(row=row, column=3, padx=2, pady=2)

        ctk.CTkLabel(input_frame, text="Students/Lecture:").grid(row=row, column=4, padx=2, pady=2, sticky="e")
        self.course_students = ctk.CTkEntry(input_frame, width=50)
        self.course_students.grid(row=row, column=5, padx=2, pady=2)

        row += 1
        self.course_lab_var = ctk.BooleanVar()
        ctk.CTkCheckBox(input_frame, text="Requires Lab", variable=self.course_lab_var).grid(row=row, column=0, columnspan=2, pady=5)

        btn_frame = ctk.CTkFrame(tab)
        btn_frame.pack(fill="x", padx=5, pady=5)

        def add_course():
            try:
                title = self.course_title.get()
                dept = self.course_dept.get()
                year = int(self.course_year.get())
                lectures = int(self.course_lectures.get())
                duration = int(self.course_duration.get())
                students = int(self.course_students.get())
                lab = 1 if self.course_lab_var.get() else 0
                if year<1 or year>5: raise ValueError("Year 1-5")
                if lectures<1 or duration<1 or students<1: raise ValueError("All numbers must be >=1")
                with db_manager.get_connection() as conn:
                    conn.execute(
                        """INSERT INTO courses (title, department, year_level, lectures_per_week, duration,
                           students_per_lecture, requires_lab) VALUES (?,?,?,?,?,?,?)""",
                        (title, dept, year, lectures, duration, students, lab))
                refresh_treeview(tree, "SELECT * FROM courses", columns)
                messagebox.showinfo("Success", "Course added.")
            except Exception as e:
                messagebox.showerror("Error", str(e))

        def delete_course():
            selected = tree.selection()
            if not selected: return
            item = tree.item(selected[0])['values']
            cid = item[0]
            if messagebox.askyesno("Confirm", f"Delete course {item[1]}?"):
                with db_manager.get_connection() as conn:
                    conn.execute("DELETE FROM courses WHERE id=?", (cid,))
                refresh_treeview(tree, "SELECT * FROM courses", columns)

        ctk.CTkButton(btn_frame, text="Add", command=add_course).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="Delete", command=delete_course).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="Refresh", command=lambda: refresh_treeview(tree, "SELECT * FROM courses", columns)).pack(side="left", padx=5)

        refresh_treeview(tree, "SELECT * FROM courses", columns)

    # ------------------------------------------------------------------
    # Enrollments Tab
    # ------------------------------------------------------------------
    def _build_enrollments_tab(self):
        tab = self.tabs["Enrollments"]
        frame = ctk.CTkFrame(tab)
        frame.pack(fill="both", expand=True, padx=5, pady=5)

        columns = ("student_id", "course_id")
        tree = ttk.Treeview(frame, columns=columns, show="headings")
        tree.heading("student_id", text="Student ID")
        tree.heading("course_id", text="Course ID")
        tree.pack(fill="both", expand=True, side="left")

        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        scrollbar.pack(side="right", fill="y")
        tree.configure(yscrollcommand=scrollbar.set)

        input_frame = ctk.CTkFrame(tab)
        input_frame.pack(fill="x", padx=5, pady=5)

        ctk.CTkLabel(input_frame, text="Student ID:").grid(row=0, column=0, padx=2, pady=2, sticky="e")
        self.enroll_student_id = ctk.CTkEntry(input_frame, width=80)
        self.enroll_student_id.grid(row=0, column=1, padx=2, pady=2)

        ctk.CTkLabel(input_frame, text="Course ID:").grid(row=0, column=2, padx=2, pady=2, sticky="e")
        self.enroll_course_id = ctk.CTkEntry(input_frame, width=80)
        self.enroll_course_id.grid(row=0, column=3, padx=2, pady=2)

        btn_frame = ctk.CTkFrame(tab)
        btn_frame.pack(fill="x", padx=5, pady=5)

        def add_enrollment():
            try:
                sid = int(self.enroll_student_id.get())
                cid = int(self.enroll_course_id.get())
                with db_manager.get_connection() as conn:
                    conn.execute("INSERT INTO enrollment (student_id, course_id) VALUES (?,?)", (sid, cid))
                refresh_treeview(tree, "SELECT student_id, course_id FROM enrollment", columns)
                messagebox.showinfo("Success", "Enrollment added.")
            except Exception as e:
                messagebox.showerror("Error", str(e))

        def delete_enrollment():
            selected = tree.selection()
            if not selected: return
            item = tree.item(selected[0])['values']
            sid, cid = item[0], item[1]
            if messagebox.askyesno("Confirm", f"Delete enrollment (student {sid}, course {cid})?"):
                with db_manager.get_connection() as conn:
                    conn.execute("DELETE FROM enrollment WHERE student_id=? AND course_id=?", (sid, cid))
                refresh_treeview(tree, "SELECT student_id, course_id FROM enrollment", columns)

        ctk.CTkButton(btn_frame, text="Add", command=add_enrollment).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="Delete", command=delete_enrollment).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="Refresh", command=lambda: refresh_treeview(tree, "SELECT student_id, course_id FROM enrollment", columns)).pack(side="left", padx=5)

        refresh_treeview(tree, "SELECT student_id, course_id FROM enrollment", columns)

    # ------------------------------------------------------------------
    # Teacher Assignments Tab
    # ------------------------------------------------------------------
    def _build_teacher_assignments_tab(self):
        tab = self.tabs["Teacher Assignments"]
        frame = ctk.CTkFrame(tab)
        frame.pack(fill="both", expand=True, padx=5, pady=5)

        columns = ("teacher_id", "course_id", "preferred_room_id")
        tree = ttk.Treeview(frame, columns=columns, show="headings")
        tree.heading("teacher_id", text="Teacher ID")
        tree.heading("course_id", text="Course ID")
        tree.heading("preferred_room_id", text="Pref Room ID")
        tree.pack(fill="both", expand=True, side="left")

        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        scrollbar.pack(side="right", fill="y")
        tree.configure(yscrollcommand=scrollbar.set)

        input_frame = ctk.CTkFrame(tab)
        input_frame.pack(fill="x", padx=5, pady=5)

        ctk.CTkLabel(input_frame, text="Teacher ID:").grid(row=0, column=0, padx=2, pady=2, sticky="e")
        self.ta_teacher_id = ctk.CTkEntry(input_frame, width=80)
        self.ta_teacher_id.grid(row=0, column=1, padx=2, pady=2)

        ctk.CTkLabel(input_frame, text="Course ID:").grid(row=0, column=2, padx=2, pady=2, sticky="e")
        self.ta_course_id = ctk.CTkEntry(input_frame, width=80)
        self.ta_course_id.grid(row=0, column=3, padx=2, pady=2)

        ctk.CTkLabel(input_frame, text="Pref Room ID (opt):").grid(row=0, column=4, padx=2, pady=2, sticky="e")
        self.ta_pref_room = ctk.CTkEntry(input_frame, width=80)
        self.ta_pref_room.grid(row=0, column=5, padx=2, pady=2)

        btn_frame = ctk.CTkFrame(tab)
        btn_frame.pack(fill="x", padx=5, pady=5)

        def add_assignment():
            try:
                tid = int(self.ta_teacher_id.get())
                cid = int(self.ta_course_id.get())
                pref = self.ta_pref_room.get()
                pref = int(pref) if pref.strip() else None
                with db_manager.get_connection() as conn:
                    conn.execute(
                        "INSERT INTO teacher_assignments (teacher_id, course_id, preferred_room_id) VALUES (?,?,?)",
                        (tid, cid, pref))
                refresh_treeview(tree, "SELECT teacher_id, course_id, preferred_room_id FROM teacher_assignments", columns)
                messagebox.showinfo("Success", "Assignment added.")
            except Exception as e:
                messagebox.showerror("Error", str(e))

        def delete_assignment():
            selected = tree.selection()
            if not selected: return
            item = tree.item(selected[0])['values']
            tid, cid = item[0], item[1]
            if messagebox.askyesno("Confirm", f"Delete assignment (teacher {tid}, course {cid})?"):
                with db_manager.get_connection() as conn:
                    conn.execute("DELETE FROM teacher_assignments WHERE teacher_id=? AND course_id=?", (tid, cid))
                refresh_treeview(tree, "SELECT teacher_id, course_id, preferred_room_id FROM teacher_assignments", columns)

        ctk.CTkButton(btn_frame, text="Add", command=add_assignment).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="Delete", command=delete_assignment).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="Refresh", command=lambda: refresh_treeview(tree, "SELECT teacher_id, course_id, preferred_room_id FROM teacher_assignments", columns)).pack(side="left", padx=5)

        refresh_treeview(tree, "SELECT teacher_id, course_id, preferred_room_id FROM teacher_assignments", columns)

    # ------------------------------------------------------------------
    # Availability Tabs (generic helper)
    # ------------------------------------------------------------------
    def _build_availability_tab(self, tab_name: str, table: str, entity_label: str):
        tab = self.tabs[tab_name]
        frame = ctk.CTkFrame(tab)
        frame.pack(fill="both", expand=True, padx=5, pady=5)

        columns = ("id", "entity_id", "day", "start_period", "end_period")
        tree = ttk.Treeview(frame, columns=columns, show="headings")
        for col in columns:
            tree.heading(col, text=col.replace("_", " ").title())
        tree.pack(fill="both", expand=True, side="left")

        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        scrollbar.pack(side="right", fill="y")
        tree.configure(yscrollcommand=scrollbar.set)

        input_frame = ctk.CTkFrame(tab)
        input_frame.pack(fill="x", padx=5, pady=5)

        ctk.CTkLabel(input_frame, text=f"{entity_label} ID:").grid(row=0, column=0, padx=2, pady=2, sticky="e")
        entity_id_entry = ctk.CTkEntry(input_frame, width=80)
        entity_id_entry.grid(row=0, column=1, padx=2, pady=2)

        ctk.CTkLabel(input_frame, text="Day (1-7):").grid(row=0, column=2, padx=2, pady=2, sticky="e")
        day_entry = ctk.CTkEntry(input_frame, width=50)
        day_entry.grid(row=0, column=3, padx=2, pady=2)

        ctk.CTkLabel(input_frame, text="Start Period:").grid(row=0, column=4, padx=2, pady=2, sticky="e")
        start_entry = ctk.CTkEntry(input_frame, width=50)
        start_entry.grid(row=0, column=5, padx=2, pady=2)

        ctk.CTkLabel(input_frame, text="End Period:").grid(row=0, column=6, padx=2, pady=2, sticky="e")
        end_entry = ctk.CTkEntry(input_frame, width=50)
        end_entry.grid(row=0, column=7, padx=2, pady=2)

        btn_frame = ctk.CTkFrame(tab)
        btn_frame.pack(fill="x", padx=5, pady=5)

        def add_avail():
            try:
                eid = int(entity_id_entry.get())
                day = int(day_entry.get())
                start = int(start_entry.get())
                end = int(end_entry.get())
                if day < 1 or day > 7: raise ValueError("Day 1-7")
                if start < 1 or end < start: raise ValueError("Invalid periods")
                with db_manager.get_connection() as conn:
                    conn.execute(
                        f"INSERT INTO {table} (entity_id, day, start_period, end_period) VALUES (?,?,?,?)",
                        (eid, day, start, end))
                refresh_treeview(tree, f"SELECT * FROM {table}", columns)
                messagebox.showinfo("Success", "Availability added.")
            except Exception as e:
                messagebox.showerror("Error", str(e))

        def delete_avail():
            selected = tree.selection()
            if not selected: return
            item = tree.item(selected[0])['values']
            avail_id = item[0]
            if messagebox.askyesno("Confirm", f"Delete availability record {avail_id}?"):
                with db_manager.get_connection() as conn:
                    conn.execute(f"DELETE FROM {table} WHERE id=?", (avail_id,))
                refresh_treeview(tree, f"SELECT * FROM {table}", columns)

        ctk.CTkButton(btn_frame, text="Add", command=add_avail).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="Delete", command=delete_avail).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="Refresh", command=lambda: refresh_treeview(tree, f"SELECT * FROM {table}", columns)).pack(side="left", padx=5)

        refresh_treeview(tree, f"SELECT * FROM {table}", columns)

    def _build_student_availability_tab(self):
        self._build_availability_tab("Student Availability", "student_availability", "Student")

    def _build_teacher_availability_tab(self):
        self._build_availability_tab("Teacher Availability", "teacher_availability", "Teacher")

    def _build_room_availability_tab(self):
        self._build_availability_tab("Room Availability", "room_availability", "Room")

    # ------------------------------------------------------------------
    # Solver Config Tab
    # ------------------------------------------------------------------
    def _build_solver_config_tab(self):
        tab = self.tabs["Solver Config"]
        frame = ctk.CTkFrame(tab)
        frame.pack(fill="both", expand=True, padx=5, pady=5)

        # Load current config
        config = db_manager.load_solver_config()

        ctk.CTkLabel(frame, text="Slots per Day:").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        self.cfg_slots = ctk.CTkEntry(frame, width=80)
        self.cfg_slots.insert(0, str(config.slots_per_day))
        self.cfg_slots.grid(row=0, column=1, padx=5, pady=5)

        ctk.CTkLabel(frame, text="Days per Week:").grid(row=1, column=0, padx=5, pady=5, sticky="e")
        self.cfg_days = ctk.CTkEntry(frame, width=80)
        self.cfg_days.insert(0, str(config.days_per_week))
        self.cfg_days.grid(row=1, column=1, padx=5, pady=5)

        ctk.CTkLabel(frame, text="Time Limit (s):").grid(row=2, column=0, padx=5, pady=5, sticky="e")
        self.cfg_time = ctk.CTkEntry(frame, width=80)
        self.cfg_time.insert(0, str(config.time_limit_seconds))
        self.cfg_time.grid(row=2, column=1, padx=5, pady=5)

        self.cfg_prevent_var = ctk.BooleanVar(value=config.prevent_same_day)
        ctk.CTkCheckBox(frame, text="Prevent Same Day", variable=self.cfg_prevent_var).grid(row=3, column=0, columnspan=2, pady=10)

        def save_config():
            try:
                config.slots_per_day = int(self.cfg_slots.get())
                config.days_per_week = int(self.cfg_days.get())
                config.time_limit_seconds = float(self.cfg_time.get())
                config.prevent_same_day = self.cfg_prevent_var.get()
                db_manager.save_solver_config(config)
                messagebox.showinfo("Success", "Configuration saved.")
            except Exception as e:
                messagebox.showerror("Error", str(e))

        ctk.CTkButton(frame, text="Save Config", command=save_config).grid(row=4, column=0, columnspan=2, pady=20)

    # ------------------------------------------------------------------
    # Mock Data Tab
    # ------------------------------------------------------------------
    def _build_mock_data_tab(self):
        tab = self.tabs["Mock Data"]
        frame = ctk.CTkFrame(tab)
        frame.pack(fill="both", expand=True, padx=5, pady=5)

        ctk.CTkLabel(frame, text="Generate Mock Data (overwrites existing data)", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=10)

        # Parameter entries
        ctk.CTkLabel(frame, text="Students:").pack(pady=2)
        self.mock_students = ctk.CTkEntry(frame, width=100)
        self.mock_students.insert(0, "1000")
        self.mock_students.pack(pady=2)

        ctk.CTkLabel(frame, text="Teachers:").pack(pady=2)
        self.mock_teachers = ctk.CTkEntry(frame, width=100)
        self.mock_teachers.insert(0, "100")
        self.mock_teachers.pack(pady=2)

        ctk.CTkLabel(frame, text="Rooms:").pack(pady=2)
        self.mock_rooms = ctk.CTkEntry(frame, width=100)
        self.mock_rooms.insert(0, "60")
        self.mock_rooms.pack(pady=2)

        ctk.CTkLabel(frame, text="Courses:").pack(pady=2)
        self.mock_courses = ctk.CTkEntry(frame, width=100)
        self.mock_courses.insert(0, "120")
        self.mock_courses.pack(pady=2)

        ctk.CTkLabel(frame, text="Difficulty:").pack(pady=2)
        self.mock_difficulty = ctk.CTkComboBox(frame, values=["easy", "normal", "hard"], width=120)
        self.mock_difficulty.set("normal")
        self.mock_difficulty.pack(pady=2)

        ctk.CTkLabel(frame, text="Seed:").pack(pady=2)
        self.mock_seed = ctk.CTkEntry(frame, width=100)
        self.mock_seed.insert(0, "42")
        self.mock_seed.pack(pady=2)

        def generate():
            try:
                students = int(self.mock_students.get())
                teachers = int(self.mock_teachers.get())
                rooms = int(self.mock_rooms.get())
                courses = int(self.mock_courses.get())
                difficulty = self.mock_difficulty.get()
                seed = int(self.mock_seed.get())
                # Clear first
                if messagebox.askyesno("Confirm", "This will delete all existing data and generate new mock data. Continue?"):
                    generate_all_mock_data(
                        student_count=students,
                        teacher_count=teachers,
                        room_count=rooms,
                        course_count=courses,
                        clear_first=True,
                        seed=seed,
                        difficulty=difficulty
                    )
                    messagebox.showinfo("Done", "Mock data generated. Refresh other tabs to see changes.")
            except Exception as e:
                messagebox.showerror("Error", str(e))

        ctk.CTkButton(frame, text="Generate Mock Data", command=generate, fg_color="green").pack(pady=20)

# ----------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------
if __name__ == "__main__":
    # Initialize database (ensures schema exists)
    db_manager._init_database()
    app = App()
    app.mainloop()
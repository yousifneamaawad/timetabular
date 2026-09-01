# app.py
"""
University Timetable Scheduler - CustomTkinter Desktop Application
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import logging
from pathlib import Path

from database import db_manager
from models import SolverConfig, SolverWeights
from solver import solve_schedule
from statistics import StatisticsCalculator
from exporter import ScheduleExporter

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Set CustomTkinter appearance
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class SchedulerApp(ctk.CTk):
    """Main application window."""

    def __init__(self):
        super().__init__()

        # Load scheduler configuration from the database
        self.config = db_manager.load_solver_config()
        self.weights = SolverWeights()
        self.is_solving = False
        self.cancel_requested = False
        
        # Window setup
        self.title("University Timetable Scheduler")
        self.geometry("1400x850")
        self.minsize(1200, 700)
        
        # Configure grid
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        # Build UI
        self._build_sidebar()
        self._build_main_area()
        self._build_statusbar()
        
        # Show dashboard by default
        self._show_dashboard()
        
        # Initialize database
        try:
            db_manager._init_database()
        except Exception as e:
            logger.warning(f"Database init warning: {e}")
    
    def _build_sidebar(self):
        """Build navigation sidebar."""
        sidebar = ctk.CTkFrame(self, width=220, corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        
        # App title
        title_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        title_frame.pack(fill="x", padx=16, pady=(20, 10))
        
        ctk.CTkLabel(
            title_frame,
            text="📅 Scheduler",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).pack(anchor="w")
        
        ctk.CTkLabel(
            title_frame,
            text="University Timetable",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        ).pack(anchor="w")
        
        # Separator
        ctk.CTkFrame(sidebar, height=1, fg_color="gray").pack(fill="x", padx=16, pady=10)
        
        # Navigation buttons
        nav_buttons = [
            ("Dashboard", "📊", self._show_dashboard),
            ("Timetable", "📅", self._show_timetable),
            ("Reports", "📈", self._show_reports),
            ("Settings", "⚙️", self._show_settings),
        ]
        
        self.nav_buttons = {}
        for text, icon, command in nav_buttons:
            btn = ctk.CTkButton(
                sidebar,
                text=f"{icon}  {text}",
                anchor="w",
                height=40,
                fg_color="transparent",
                hover_color=("gray70", "gray30"),
                command=command,
                font=ctk.CTkFont(size=13),
            )
            btn.pack(fill="x", padx=8, pady=2)
            self.nav_buttons[text.lower()] = btn
    
    def _build_main_area(self):
        """Build main content area."""
        self.main_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=24, pady=24)
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(0, weight=1)
    
    def _build_statusbar(self):
        """Build status bar."""
        statusbar = ctk.CTkFrame(self, height=32, corner_radius=0)
        statusbar.grid(row=1, column=0, columnspan=2, sticky="ew")
        
        self.status_label = ctk.CTkLabel(
            statusbar,
            text="Ready",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        )
        self.status_label.pack(side="left", padx=16)
        
        ctk.CTkLabel(
            statusbar,
            text="v1.0.0",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        ).pack(side="right", padx=16)
    
    def _clear_main_frame(self):
        """Clear the main content frame."""
        for widget in self.main_frame.winfo_children():
            widget.destroy()
    
    def _show_dashboard(self):
        """Show dashboard view."""
        self._clear_main_frame()
        
        # Scrollable frame
        scroll_frame = ctk.CTkScrollableFrame(self.main_frame, fg_color="transparent")
        scroll_frame.pack(fill="both", expand=True)
        
        # Header
        header = ctk.CTkFrame(scroll_frame, fg_color="transparent")
        header.pack(fill="x", pady=(0, 20))
        
        ctk.CTkLabel(
            header,
            text="Dashboard",
            font=ctk.CTkFont(size=24, weight="bold"),
        ).pack(side="left")
        
        ctk.CTkButton(
            header,
            text="🔄 Refresh",
            width=100,
            command=self._show_dashboard,
        ).pack(side="right")
        
        # Statistics
        try:
            calc = StatisticsCalculator()
            stats = calc.compute_all()
            
            if stats.total_lectures == 0:
                self._show_empty_state(scroll_frame, "No Schedule Data", 
                                       "Generate mock data and run the optimizer to see statistics.")
                return
            
            # Summary cards
            cards_frame = ctk.CTkFrame(scroll_frame, fg_color="transparent")
            cards_frame.pack(fill="x", pady=(0, 20))
            
            cards = [
                ("Total Lectures", stats.total_lectures, "#3B82F6"),
                ("Courses", stats.total_courses, "#10B981"),
                ("Teachers", stats.total_teachers, "#F59E0B"),
                ("Students", stats.total_students, "#8B5CF6"),
            ]
            
            for title, value, color in cards:
                card = ctk.CTkFrame(cards_frame, corner_radius=12)
                card.pack(side="left", padx=8, fill="both", expand=True)
                
                ctk.CTkLabel(
                    card,
                    text=str(value),
                    font=ctk.CTkFont(size=28, weight="bold"),
                    text_color=color,
                ).pack(anchor="w", padx=20, pady=(20, 0))
                
                ctk.CTkLabel(
                    card,
                    text=title,
                    font=ctk.CTkFont(size=12),
                    text_color="gray",
                ).pack(anchor="w", padx=20, pady=(0, 20))
            
            # Metrics section
            metrics_frame = ctk.CTkFrame(scroll_frame, fg_color="transparent")
            metrics_frame.pack(fill="x")
            
            # Room utilization
            room_frame = ctk.CTkFrame(metrics_frame, corner_radius=12)
            room_frame.pack(side="left", padx=8, fill="both", expand=True)
            
            ctk.CTkLabel(
                room_frame,
                text="Room Utilization",
                font=ctk.CTkFont(size=14, weight="bold"),
            ).pack(anchor="w", padx=16, pady=(16, 8))
            
            for name, util in list(stats.room_utilization.items())[:8]:
                self._create_progress_bar(room_frame, name[:25], util)
            
            # Teacher workload
            teacher_frame = ctk.CTkFrame(metrics_frame, corner_radius=12)
            teacher_frame.pack(side="left", padx=8, fill="both", expand=True)
            
            ctk.CTkLabel(
                teacher_frame,
                text="Teacher Workload",
                font=ctk.CTkFont(size=14, weight="bold"),
            ).pack(anchor="w", padx=16, pady=(16, 8))
            
            for name, periods in list(stats.teacher_workload.items())[:8]:
                row = ctk.CTkFrame(teacher_frame, fg_color="transparent")
                row.pack(fill="x", padx=16, pady=2)
                
                ctk.CTkLabel(row, text=name[:25], font=ctk.CTkFont(size=11)).pack(side="left")
                ctk.CTkLabel(
                    row, 
                    text=f"{periods} periods",
                    font=ctk.CTkFont(size=11),
                    text_color="gray",
                ).pack(side="right")
        
        except Exception as e:
            self._show_empty_state(scroll_frame, "Error", str(e))
    
    def _show_timetable(self):
        """Show timetable grid view."""
        self._clear_main_frame()
        
        # Header
        header = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        header.pack(fill="x", pady=(0, 16))
        
        ctk.CTkLabel(
            header,
            text="Timetable",
            font=ctk.CTkFont(size=24, weight="bold"),
        ).pack(side="left")
        
        # Export buttons
        for fmt, text in [("excel", "📊 Excel"), ("pdf", "📄 PDF"), ("csv", "📝 CSV")]:
            ctk.CTkButton(
                header,
                text=text,
                width=90,
                command=lambda f=fmt: self.export_schedule(f),
            ).pack(side="right", padx=4)
        
        # Timetable grid
        grid_frame = ctk.CTkScrollableFrame(self.main_frame, fg_color="#2B2B2B", corner_radius=12)
        grid_frame.pack(fill="both", expand=True)
        
        try:
            with db_manager.get_connection() as conn:
                config = conn.execute("SELECT * FROM solver_config WHERE id = 1").fetchone()
                days = config['days_per_week'] if config else 5
                slots = config['slots_per_day'] if config else 8
                
                entries = conn.execute("""
                    SELECT s.*, c.title as course_title, t.full_name as teacher_name, r.room_name
                    FROM schedule s
                    JOIN courses c ON s.course_id = c.id
                    JOIN teachers t ON s.teacher_id = t.id
                    JOIN rooms r ON s.room_id = r.id
                    ORDER BY s.day, s.start_period
                """).fetchall()
            
            if not entries:
                ctk.CTkLabel(
                    grid_frame,
                    text="No schedule data available",
                    font=ctk.CTkFont(size=14),
                    text_color="gray",
                ).pack(pady=40)
                return
            
            # Build grid
            from collections import defaultdict
            schedule = defaultdict(lambda: defaultdict(list))
            for e in entries:
                schedule[e['day']][e['start_period']].append(dict(e))
            
            day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
            
            # Header row
            header_row = ctk.CTkFrame(grid_frame, fg_color="transparent")
            header_row.pack(fill="x", pady=(8, 4))
            
            ctk.CTkLabel(header_row, text="Period", width=80, font=ctk.CTkFont(size=11, weight="bold")).pack(side="left", padx=2)
            for day in range(days):
                ctk.CTkLabel(
                    header_row,
                    text=day_names[day],
                    font=ctk.CTkFont(size=11, weight="bold"),
                ).pack(side="left", padx=2, fill="x", expand=True)
            
            # Period rows
            for period in range(1, slots + 1):
                row = ctk.CTkFrame(grid_frame, fg_color="transparent")
                row.pack(fill="x", pady=1)
                
                ctk.CTkLabel(row, text=f"P{period}", width=80, font=ctk.CTkFont(size=10)).pack(side="left", padx=2)
                
                for day in range(1, days + 1):
                    cell_entries = schedule[day][period]
                    cell = ctk.CTkFrame(row, corner_radius=4, fg_color="#1E1E1E" if cell_entries else "#2B2B2B")
                    cell.pack(side="left", padx=2, fill="both", expand=True)
                    
                    if cell_entries:
                        for entry in cell_entries[:2]:
                            ctk.CTkLabel(
                                cell,
                                text=entry['course_title'][:22],
                                font=ctk.CTkFont(size=9, weight="bold"),
                                text_color="#93C5FD",
                            ).pack(anchor="w", padx=4, pady=1)
                            ctk.CTkLabel(
                                cell,
                                text=f"Room: {entry['room_name']}",
                                font=ctk.CTkFont(size=8),
                                text_color="gray",
                            ).pack(anchor="w", padx=4)
                    else:
                        ctk.CTkLabel(cell, text="", height=50).pack()
        
        except Exception as e:
            ctk.CTkLabel(
                grid_frame,
                text=f"Error loading timetable: {e}",
                text_color="red",
            ).pack(pady=20)
    
    def _show_reports(self):
        """Show reports view."""
        self._clear_main_frame()
        
        header = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        header.pack(fill="x", pady=(0, 16))
        
        ctk.CTkLabel(
            header,
            text="Reports",
            font=ctk.CTkFont(size=24, weight="bold"),
        ).pack(side="left")
        
        content = ctk.CTkFrame(self.main_frame, corner_radius=12, fg_color="#2B2B2B")
        content.pack(fill="both", expand=True)
        
        ctk.CTkLabel(
            content,
            text="📈",
            font=ctk.CTkFont(size=48),
        ).pack(pady=(60, 10))
        
        ctk.CTkLabel(
            content,
            text="Export your schedule in various formats",
            font=ctk.CTkFont(size=14),
            text_color="gray",
        ).pack()
        
        btn_frame = ctk.CTkFrame(content, fg_color="transparent")
        btn_frame.pack(pady=20)
        
        for fmt, text in [("excel", "Export to Excel"), ("pdf", "Export to PDF"), ("csv", "Export to CSV")]:
            ctk.CTkButton(
                btn_frame,
                text=text,
                width=150,
                command=lambda f=fmt: self.export_schedule(f),
            ).pack(side="left", padx=8)
        
    def _save_configuration(self):
        """Save scheduler configuration to the database."""

        try:
            config = db_manager.load_solver_config()

            config.slots_per_day = int(self.slots_var.get())
            config.days_per_week = int(self.days_var.get())
            config.time_limit_seconds = float(self.timeout_var.get())
            config.prevent_same_day = self.same_day_var.get()

            db_manager.save_solver_config(config)
            self.config = db_manager.load_solver_config()
            self.solver_status.configure(
                text="Configuration saved successfully.",
                text_color="#10B981",
            )

        except ValueError:
            messagebox.showerror(
                "Error",
                "Please enter valid configuration values."
            )

        except Exception as e:
            messagebox.showerror("Error", str(e))










    def _show_settings(self):
        """Show settings/control panel."""
        self._clear_main_frame()
        
        scroll_frame = ctk.CTkScrollableFrame(self.main_frame, fg_color="transparent")
        scroll_frame.pack(fill="both", expand=True)
        
        ctk.CTkLabel(
            scroll_frame,
            text="Solver Settings",
            font=ctk.CTkFont(size=24, weight="bold"),
        ).pack(anchor="w", pady=(0, 16))
        
        # Parameters
        params_frame = ctk.CTkFrame(scroll_frame, corner_radius=12)
        params_frame.pack(fill="x", pady=(0, 12))
        
        ctk.CTkLabel(
            params_frame,
            text="Schedule Parameters",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", padx=16, pady=(16, 8))
        
        inputs_frame = ctk.CTkFrame(params_frame, fg_color="transparent")
        inputs_frame.pack(fill="x", padx=16, pady=8)
        config = db_manager.load_solver_config()

        self.slots_var = tk.StringVar(value=str(config.slots_per_day))
        self.days_var = tk.StringVar(value=str(config.days_per_week))
        self.timeout_var = tk.StringVar(value=str(config.time_limit_seconds))
        self.same_day_var = tk.BooleanVar(value=config.prevent_same_day)
        ctk.CTkButton(params_frame,text="💾 Save Configuration",command=self._save_configuration,).pack(anchor="e", padx=16, pady=(8, 16))
        for label, var in [("Periods/Day:", self.slots_var), ("Days/Week:", self.days_var), ("Time Limit (s):", self.timeout_var)]:
            row = ctk.CTkFrame(inputs_frame, fg_color="transparent")
            row.pack(side="left", padx=8)
            ctk.CTkLabel(row, text=label, font=ctk.CTkFont(size=11)).pack(side="left", padx=4)
            ctk.CTkEntry(row, textvariable=var, width=80).pack(side="left", padx=4)
        
        self.same_day_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            params_frame,
            text="Prevent same-day lectures for same course",
            variable=self.same_day_var,
        ).pack(anchor="w", padx=16, pady=8)
        
        # Solver controls
        control_frame = ctk.CTkFrame(scroll_frame, corner_radius=12)
        control_frame.pack(fill="x", pady=(0, 12))
        
        ctk.CTkLabel(
            control_frame,
            text="Solver Control",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", padx=16, pady=(16, 8))
        
        btn_frame = ctk.CTkFrame(control_frame, fg_color="transparent")
        btn_frame.pack(fill="x", padx=16, pady=8)
        
        ctk.CTkButton(
            btn_frame,
            text="▶ Optimize Schedule",
            fg_color="#2563EB",
            hover_color="#1D4ED8",
            command=self._run_solver,
        ).pack(side="left", padx=4)
        
        ctk.CTkButton(
            btn_frame,
            text="⏹ Cancel",
            fg_color="#DC2626",
            hover_color="#B91C1C",
            command=self._cancel_solver,
        ).pack(side="left", padx=4)
        
        self.solver_status = ctk.CTkLabel(
            control_frame,
            text="Ready to optimize",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        )
        self.solver_status.pack(anchor="w", padx=16, pady=8)
        
        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(control_frame, width=300)
        self.progress_bar.pack(padx=16, pady=8)
        self.progress_bar.set(0)
        
        # Database management
        db_frame = ctk.CTkFrame(scroll_frame, corner_radius=12)
        db_frame.pack(fill="x")
        
        ctk.CTkLabel(
            db_frame,
            text="Database Management",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", padx=16, pady=(16, 8))
        
        db_btn_frame = ctk.CTkFrame(db_frame, fg_color="transparent")
        db_btn_frame.pack(fill="x", padx=16, pady=8)
        
        ctk.CTkButton(
            db_btn_frame,
            text="Generate Mock Data",
            command=self._generate_mock_data,
        ).pack(side="left", padx=4)
        
        ctk.CTkButton(
            db_btn_frame,
            text="Clear Schedule",
            fg_color="#DC2626",
            hover_color="#B91C1C",
            command=self._clear_schedule,
        ).pack(side="left", padx=4)
    
    def _create_progress_bar(self, parent, label, value):
        """Create a progress bar row."""
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=2)
        
        ctk.CTkLabel(row, text=label, font=ctk.CTkFont(size=10), width=120).pack(side="left")
        
        bar = ctk.CTkProgressBar(row, width=120)
        bar.pack(side="left", padx=8)
        bar.set(value / 100 if value > 0 else 0)
        
        color = "#10B981" if value < 50 else "#F59E0B" if value < 80 else "#EF4444"
        ctk.CTkLabel(row, text=f"{value:.1f}%", font=ctk.CTkFont(size=10), text_color=color).pack(side="left")
    
    def _show_empty_state(self, parent, title, message):
        """Show empty state message."""
        ctk.CTkLabel(parent, text="", height=60).pack()  # Spacer
        ctk.CTkLabel(
            parent,
            text=title,
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="gray",
        ).pack()
        ctk.CTkLabel(
            parent,
            text=message,
            font=ctk.CTkFont(size=12),
            text_color="gray",
        ).pack()
        ctk.CTkButton(
            parent,
            text="Go to Settings",
            command=self._show_settings,
        ).pack(pady=16)
    
    def _run_solver(self):
        """Run the solver."""
        if self.is_solving:
            return
        
        try:
            self.config.slots_per_day = int(self.slots_var.get())
            self.config.days_per_week = int(self.days_var.get())
            self.config.time_limit_seconds = float(self.timeout_var.get())
            self.config.prevent_same_day = self.same_day_var.get()
        except ValueError:
            messagebox.showerror("Error", "Invalid configuration values")
            return
        
        self.is_solving = True
        self.cancel_requested = False
        self.solver_status.configure(text="Solving...", text_color="#F59E0B")
        self.progress_bar.configure(mode="indeterminate")
        self.progress_bar.start()
        
        def solver_thread():
            try:
                success, message = solve_schedule(
                    config=self.config,
                    weights=self.weights,
                    is_cancelled=lambda: self.cancel_requested
                )
                self.after(0, self._on_solver_complete, success, message)
            except Exception as e:
                self.after(0, self._on_solver_complete, False, str(e))
        
        threading.Thread(target=solver_thread, daemon=True).start()
    
    def _on_solver_complete(self, success, message):
        """Handle solver completion."""
        self.is_solving = False
        self.progress_bar.stop()
        self.progress_bar.configure(mode="determinate")
        self.progress_bar.set(1)
        
        if success:
            self.solver_status.configure(text=message, text_color="#10B981")
        else:
            self.solver_status.configure(text=message, text_color="#EF4444")
    
    def _cancel_solver(self):
        """Cancel running solver."""
        if self.is_solving:
            self.cancel_requested = True
            self.solver_status.configure(text="Cancelling...", text_color="#F59E0B")
    
    def _generate_mock_data(self):
        """Generate mock data."""

        # Update the database with the current UI settings
        try:
            self.config.slots_per_day = int(self.slots_var.get())
            self.config.days_per_week = int(self.days_var.get())
            self.config.time_limit_seconds = float(self.timeout_var.get())
            self.config.prevent_same_day = self.same_day_var.get()

            with db_manager.get_connection() as conn:
                conn.execute("""
                    UPDATE solver_config
                    SET slots_per_day = ?,
                        days_per_week = ?,
                        time_limit_seconds = ?,
                        prevent_same_day = ?
                    WHERE id = 1
                """, (
                    self.config.slots_per_day,
                    self.config.days_per_week,
                    self.config.time_limit_seconds,
                    int(self.config.prevent_same_day)
                ))
                conn.commit()

        except ValueError:
            messagebox.showerror("Error", "Invalid configuration values")
            return

        from generate_mock_data import generate_all_mock_data
        generate_all_mock_data(clear_first=True)

        self.solver_status.configure(
            text="Mock data generated successfully",
            text_color="#10B981"
        )
    def _clear_schedule(self):
        """Clear schedule."""
        with db_manager.get_connection() as conn:
            conn.execute("DELETE FROM schedule")
            conn.commit()
        self.solver_status.configure(text="Schedule cleared", text_color="#3B82F6")
    
    def export_schedule(self, format_type):
        """Export schedule."""
        try:
            exporter = ScheduleExporter()
            
            if format_type == "csv":
                filepath = exporter.export_csv()
            elif format_type == "excel":
                filepath = exporter.export_excel()
            elif format_type == "pdf":
                filepath = exporter.export_pdf()
            else:
                raise ValueError(f"Unknown format: {format_type}")
            
            messagebox.showinfo("Export Successful", f"File saved to:\n{filepath}")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))


def main():
    """Application entry point."""
    app = SchedulerApp()
    app.mainloop()


if __name__ == "__main__":
    main()

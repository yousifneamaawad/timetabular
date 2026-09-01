"""
ui/reports.py

Reports view for the University Scheduler.
Compatible with Flet 0.85+
"""

from typing import TYPE_CHECKING

import flet as ft

from database import db_manager
from statistics import StatisticsCalculator

if TYPE_CHECKING:
    from app import SchedulerApp


class ReportsView:
    """Reports generation and export page."""

    def __init__(self, app: "SchedulerApp"):
        self.app = app
        self.calculator = StatisticsCalculator()

        # ---------------------------------------------------------
        # Report Type
        # ---------------------------------------------------------

        self.report_type = ft.Dropdown(
            label="Report Type",
            width=250,
            options=[
                ft.dropdown.Option("teacher", "Teacher Timetable"),
                ft.dropdown.Option("student", "Student Timetable"),
                ft.dropdown.Option("room", "Room Schedule"),
                ft.dropdown.Option("course", "Course Schedule"),
                ft.dropdown.Option("department", "Department Overview"),
            ],
        )

        self.entity_selector = ft.Dropdown(
            label="Select Item",
            width=250,
            visible=False,
        )

        # ---------------------------------------------------------
        # Buttons
        # ---------------------------------------------------------

        self.generate_button = ft.FilledButton(
            text="Generate Report",
            icon=ft.Icons.DESCRIPTION,
            on_click=self._generate_report,
        )

        self.export_excel = ft.ElevatedButton(
            text="Excel",
            icon=ft.Icons.TABLE_VIEW,
            on_click=lambda e: self.app.export_schedule("excel"),
        )

        self.export_pdf = ft.ElevatedButton(
            text="PDF",
            icon=ft.Icons.PICTURE_AS_PDF,
            on_click=lambda e: self.app.export_schedule("pdf"),
        )

        self.export_csv = ft.ElevatedButton(
            text="CSV",
            icon=ft.Icons.GRID_ON,
            on_click=lambda e: self.app.export_schedule("csv"),
        )

        # ---------------------------------------------------------
        # Events
        # ---------------------------------------------------------

        self.report_type.on_change = self._on_report_type_change

        # ---------------------------------------------------------
        # Preview
        # ---------------------------------------------------------

        self.report_preview = ft.Container(
            expand=True,
            padding=20,
            border_radius=12,
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            content=ft.Column(
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                controls=[
                    ft.Icon(
                        ft.Icons.ANALYTICS,
                        size=48,
                    ),
                    ft.Text(
                        "Choose a report type to begin.",
                        size=16,
                    ),
                ],
            ),
        )
    # =============================================================
    # UI
    # =============================================================

    def _card(self, title: str, controls: list[ft.Control]):

        return ft.Container(
            padding=20,
            border_radius=12,
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            content=ft.Column(
                spacing=15,
                controls=[
                    ft.Text(
                        title,
                        size=18,
                        weight=ft.FontWeight.BOLD,
                    ),
                    *controls,
                ],
            ),
        )

    def build(self):

        return ft.Column(
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=20,
            controls=[

                ft.Text(
                    "Reports",
                    size=30,
                    weight=ft.FontWeight.BOLD,
                ),

                ft.Text(
                    "Generate reports and export timetable data.",
                    color=ft.Colors.GREY,
                ),

                ft.Divider(),

                self._card(
                    "Report Generator",
                    [

                        ft.ResponsiveRow(
                            controls=[

                                ft.Container(
                                    col={"sm":12, "md":4},
                                    content=self.report_type,
                                ),

                                ft.Container(
                                    col={"sm":12, "md":4},
                                    content=self.entity_selector,
                                ),

                                ft.Container(
                                    col={"sm":12, "md":4},
                                    alignment=ft.alignment.bottom_left,
                                    content=self.generate_button,
                                ),

                            ],
                        ),

                    ],
                ),

                self._card(
                    "Export Schedule",
                    [

                        ft.Row(
                            controls=[
                                self.export_excel,
                                self.export_pdf,
                                self.export_csv,
                            ],
                            spacing=15,
                            wrap=True,
                        ),

                    ],
                ),

                self._card(
                    "Preview",
                    [
                        self.report_preview,
                    ],
                ),

            ],
        )

    # =============================================================
    # Events
    # =============================================================

    def _on_report_type_change(self, e):

        report_type = self.report_type.value

        self.entity_selector.visible = True
        self.entity_selector.value = None
        self.entity_selector.options = []

        items = []
        with db_manager.get_connection() as conn:

            if report_type == "teacher":

                items = conn.execute(
                    "SELECT id, full_name FROM teachers ORDER BY full_name"
                ).fetchall()

                self.entity_selector.label = "Select Teacher"

            elif report_type == "student":

                items = conn.execute(
                    "SELECT id, full_name FROM students ORDER BY full_name"
                ).fetchall()

                self.entity_selector.label = "Select Student"

            elif report_type == "room":

                items = conn.execute(
                    "SELECT id, room_name FROM rooms ORDER BY room_name"
                ).fetchall()

                self.entity_selector.label = "Select Room"

            elif report_type == "course":

                items = conn.execute(
                    "SELECT id, title FROM courses ORDER BY title"
                ).fetchall()

                self.entity_selector.label = "Select Course"

            elif report_type == "department":

                self.entity_selector.visible = False
                self.app.page.update()
                return

        self.entity_selector.options = [
            ft.dropdown.Option(
                key=str(row[0]),
                text=str(row[1]),
            )
            for row in items
        ]

        self.app.page.update()

    # =============================================================
    # Report Generation
    # =============================================================

    def _generate_report(self, e):

        report_name = self.report_type.value

        if not report_name:

            self.report_preview.content = ft.Text(
                "Please select a report type.",
                color=ft.Colors.RED,
            )

            self.app.page.update()
            return

        selected = self.entity_selector.value

        preview_controls = [

            ft.Text(
                "Report Preview",
                size=22,
                weight=ft.FontWeight.BOLD,
            ),

            ft.Divider(),

            ft.Text(
                f"Report Type: {report_name.title()}",
                size=16,
            ),
        ]

        if selected:
            preview_controls.append(
                ft.Text(
                    f"Selected ID: {selected}",
                    size=15,
                )
            )

        stats = self.calculator.compute_all()

        preview_controls.extend(
            [
                ft.Divider(),
                ft.Text(
                    "Current Database Statistics",
                    size=18,
                    weight=ft.FontWeight.BOLD,
                ),
                ft.Text(f"Courses: {stats.total_courses}"),
                ft.Text(f"Teachers: {stats.total_teachers}"),
                ft.Text(f"Students: {stats.total_students}"),
                ft.Text(f"Lectures: {stats.total_lectures}"),
                ft.Text(
                    "",
                ),
                ft.Text(
                    "Use the export buttons above to save the full schedule.",
                    color=ft.Colors.GREY,
                ),
            ]
        )

        self.report_preview.content = ft.Column(
            controls=preview_controls,
            spacing=10,
            scroll=ft.ScrollMode.AUTO,
        )

        self.app.page.update()
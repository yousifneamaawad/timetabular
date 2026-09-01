# ui/timetable_grid.py

"""
Interactive timetable grid visualization.
"""

from collections import defaultdict
from typing import TYPE_CHECKING

import flet as ft

from database import db_manager

if TYPE_CHECKING:
    from app import SchedulerApp


class TimetableView:
    def __init__(self, app: "SchedulerApp"):
        self.app = app

        self.filter_student = None
        self.filter_teacher = None
        self.filter_room = None

        self.student_dropdown = None
        self.teacher_dropdown = None
        self.room_dropdown = None

        self.grid_container = None

    # ------------------------------------------------------------------

    def build(self):

        self.student_dropdown = ft.Dropdown(
            label="Student",
            width=220,
            options=self._get_student_options(),
        )
        self.student_dropdown.on_change = self._on_filter_change
        self.teacher_dropdown = ft.Dropdown(
            label="Teacher",
            width=220,
            options=self._get_teacher_options()
        )
        self.teacher_dropdown.on_change = self._on_filter_change
        self.room_dropdown = ft.Dropdown(
            label="Room",
            width=220,
            options=self._get_room_options(),
        )
        self.room_dropdown.on_change = self._on_filter_change
        self.grid_container = ft.Container(
            content=self._build_timetable_grid(),
            expand=True,
            padding=10,
            border_radius=8,
        )

        return ft.Column(
            [
                ft.Row(
                    [
                        ft.Text(
                            "Timetable",
                            size=28,
                            weight=ft.FontWeight.BOLD,
                        ),
                        ft.Row(
                            [
                                ft.IconButton(
                                    icon=ft.Icons.DOWNLOAD,
                                    tooltip="Export Excel",
                                    on_click=lambda _: self.app.export_schedule(
                                        "excel"
                                    ),
                                ),
                                ft.IconButton(
                                    icon=ft.Icons.PICTURE_AS_PDF,
                                    tooltip="Export PDF",
                                    on_click=lambda _: self.app.export_schedule(
                                        "pdf"
                                    ),
                                ),
                            ]
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Divider(),
                ft.Row(
                    [
                        self.student_dropdown,
                        self.teacher_dropdown,
                        self.room_dropdown,
                        ft.ElevatedButton(
                            "Clear Filters",
                            icon=ft.icons.CLEAR,
                            on_click=self._clear_filters,
                        ),
                    ],
                    wrap=True,
                ),
                ft.Divider(),
                self.grid_container,
            ],
            expand=True,
        )

    # ------------------------------------------------------------------

    def _refresh_grid(self):
        self.grid_container.content = self._build_timetable_grid()

        if self.grid_container.page:
            self.grid_container.update()

    # ------------------------------------------------------------------

    def _build_timetable_grid(self):

        with db_manager.get_connection() as conn:

            config = conn.execute(
                "SELECT * FROM solver_config LIMIT 1"
            ).fetchone()

            days = config["days_per_week"] if config else 5
            slots = config["slots_per_day"] if config else 8

            query = """
                SELECT
                    s.*,
                    c.title AS course_title,
                    t.full_name AS teacher_name,
                    r.room_name
                FROM schedule s
                JOIN courses c ON s.course_id = c.id
                JOIN teachers t ON s.teacher_id = t.id
                JOIN rooms r ON s.room_id = r.id
            """

            conditions = []
            params = []

            if self.filter_student:
                conditions.append("""
                    s.course_id IN (
                        SELECT course_id
                        FROM enrollment
                        WHERE student_id = ?
                    )
                """)
                params.append(self.filter_student)

            if self.filter_teacher:
                conditions.append("s.teacher_id=?")
                params.append(self.filter_teacher)

            if self.filter_room:
                conditions.append("s.room_id=?")
                params.append(self.filter_room)

            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            query += """
                ORDER BY
                s.day,
                s.start_period
            """

            rows = conn.execute(query, params).fetchall()

        schedule = defaultdict(lambda: defaultdict(list))

        for row in rows:
            schedule[row["day"]][row["start_period"]].append(dict(row))

        day_names = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]

        grid = []

        header = [
            ft.Container(
                width=90,
                padding=8,
                bgcolor=ft.Colors.BLUE_GREY_800,
                content=ft.Text(
                    "Period",
                    weight=ft.FontWeight.BOLD,
                ),
            )
        ]

        for d in range(days):
            header.append(
                ft.Container(
                    width=180,
                    padding=8,
                    alignment=ft.alignment.center,
                    bgcolor=ft.Colors.BLUE,
                    content=ft.Text(
                        day_names[d],
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.WHITE,
                    ),
                )
            )

        grid.append(ft.Row(header))

        for period in range(1, slots + 1):

            row = [
                ft.Container(
                    width=90,
                    height=90,
                    alignment=ft.alignment.center,
                    bgcolor=ft.Colors.BLUE_GREY_800,
                    content=ft.Text(
                        f"P{period}",
                        weight=ft.FontWeight.BOLD,
                    ),
                )
            ]

            for day in range(1, days + 1):

                lessons = schedule[day][period]

                if lessons:

                    controls = []

                    for lesson in lessons:

                        controls.append(
                            ft.Container(
                                bgcolor=ft.Colors.BLUE_100,
                                border_radius=6,
                                padding=4,
                                margin=2,
                                content=ft.Column(
                                    [
                                        ft.Text(
                                            lesson["course_title"],
                                            size=11,
                                            weight=ft.FontWeight.BOLD,
                                        ),
                                        ft.Text(
                                            lesson["teacher_name"],
                                            size=10,
                                        ),
                                        ft.Text(
                                            lesson["room_name"],
                                            size=10,
                                        ),
                                    ],
                                    spacing=1,
                                ),
                            )
                        )

                    content = ft.Column(
                        controls,
                        spacing=2,
                        scroll=ft.ScrollMode.AUTO,
                    )

                else:

                    content = ft.Container()

                row.append(
                    ft.Container(
                        width=180,
                        height=90,
                        padding=4,
                        border=ft.border.all(
                            1,
                            ft.Colors.GREY_300,
                        ),
                        content=content,
                    )
                )

            grid.append(ft.Row(row))

        return ft.Row(
            [
                ft.Column(
                    grid,
                    spacing=2,
                )
            ],
            scroll=ft.ScrollMode.AUTO,
        )

    # ------------------------------------------------------------------

    def _get_student_options(self):

        with db_manager.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, full_name
                FROM students
                ORDER BY full_name
                """
            ).fetchall()

        return [
            ft.dropdown.Option(str(r["id"]), r["full_name"])
            for r in rows
        ]

    # ------------------------------------------------------------------

    def _get_teacher_options(self):

        with db_manager.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, full_name
                FROM teachers
                ORDER BY full_name
                """
            ).fetchall()

        return [
            ft.dropdown.Option(str(r["id"]), r["full_name"])
            for r in rows
        ]

    # ------------------------------------------------------------------

    def _get_room_options(self):

        with db_manager.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, room_name
                FROM rooms
                ORDER BY room_name
                """
            ).fetchall()

        return [
            ft.dropdown.Option(str(r["id"]), r["room_name"])
            for r in rows
        ]

    # ------------------------------------------------------------------

    def _on_filter_change(self, e):

        self.filter_student = (
            int(self.student_dropdown.value)
            if self.student_dropdown.value
            else None
        )

        self.filter_teacher = (
            int(self.teacher_dropdown.value)
            if self.teacher_dropdown.value
            else None
        )

        self.filter_room = (
            int(self.room_dropdown.value)
            if self.room_dropdown.value
            else None
        )

        self._refresh_grid()

    # ------------------------------------------------------------------

    def _clear_filters(self, e):

        self.filter_student = None
        self.filter_teacher = None
        self.filter_room = None

        self.student_dropdown.value = None
        self.teacher_dropdown.value = None
        self.room_dropdown.value = None

        if self.app.page:
            self.app.page.update()


        self._refresh_grid()
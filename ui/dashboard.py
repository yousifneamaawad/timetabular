"""
ui/dashboard.py

Dashboard view for the University Timetable Scheduler.
Compatible with Flet 0.85+
"""

from typing import TYPE_CHECKING

import flet as ft

from statistics import StatisticsCalculator

if TYPE_CHECKING:
    from app import SchedulerApp


class DashboardView:
    """Dashboard showing overall scheduler statistics."""

    def __init__(self, app: "SchedulerApp"):
        self.app = app
        self.calculator = StatisticsCalculator()

    def build(self):

        stats = self.calculator.compute_all()

        return ft.Column(
            expand=True,
            spacing=20,
            scroll=ft.ScrollMode.AUTO,
            controls=[
                ft.Text(
                    "Dashboard",
                    size=30,
                    weight=ft.FontWeight.BOLD,
                ),
                ft.Text(
                    "Schedule overview and statistics",
                    color=ft.Colors.GREY,
                ),
                ft.Divider(),

                ft.ResponsiveRow(
                    controls=[
                        self._stat_card(
                            "Total Lectures",
                            stats.total_lectures,
                            ft.Icons.CALENDAR_MONTH,
                            ft.Colors.BLUE,
                        ),
                        self._stat_card(
                            "Courses",
                            stats.total_courses,
                            ft.Icons.MENU_BOOK,
                            ft.Colors.GREEN,
                        ),
                        self._stat_card(
                            "Teachers",
                            stats.total_teachers,
                            ft.Icons.PERSON,
                            ft.Colors.ORANGE,
                        ),
                        self._stat_card(
                            "Students",
                            stats.total_students,
                            ft.Icons.GROUPS,
                            ft.Colors.PURPLE,
                        ),
                    ]
                ),

                ft.ResponsiveRow(
                    controls=[
                        self._room_utilization_card(stats),
                        self._teacher_workload_card(stats),
                    ]
                ),
            ],
        )

    ####################################################################
    # Cards
    ####################################################################

    def _stat_card(
        self,
        title: str,
        value: int,
        icon,
        color,
    ):

        return ft.Container(
            col={"sm": 12, "md": 6, "xl": 3},
            padding=20,
            border_radius=12,
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            content=ft.Row(
                spacing=15,
                controls=[
                    ft.Icon(
                        icon,
                        size=38,
                        color=color,
                    ),
                    ft.Column(
                        spacing=2,
                        controls=[
                            ft.Text(
                                str(value),
                                size=26,
                                weight=ft.FontWeight.BOLD,
                            ),
                            ft.Text(
                                title,
                                color=ft.Colors.GREY,
                            ),
                        ],
                    ),
                ],
            ),
        )

    ####################################################################

    def _room_utilization_card(self, stats):

        controls = [
            ft.Text(
                "Room Utilization",
                size=18,
                weight=ft.FontWeight.BOLD,
            ),
            ft.Divider(),
        ]

        for room, util in list(stats.room_utilization.items())[:10]:

            controls.append(
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        ft.Text(room, width=140),
                        ft.ProgressBar(
                            value=util / 100,
                            width=180,
                        ),
                        ft.Text(f"{util:.1f}%"),
                    ],
                )
            )

        return ft.Container(
            col={"sm": 12, "lg": 6},
            padding=20,
            border_radius=12,
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            content=ft.Column(
                spacing=8,
                controls=controls,
            ),
        )

    ####################################################################

    def _teacher_workload_card(self, stats):

        controls = [
            ft.Text(
                "Teacher Workload",
                size=18,
                weight=ft.FontWeight.BOLD,
            ),
            ft.Divider(),
        ]

        for teacher, periods in list(stats.teacher_workload.items())[:10]:

            controls.append(
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        ft.Text(
                            teacher,
                            width=180,
                        ),
                        ft.Container(
                            bgcolor=ft.Colors.BLUE_100,
                            border_radius=8,
                            padding=8,
                            content=ft.Text(
                                f"{periods} periods",
                                weight=ft.FontWeight.BOLD,
                            ),
                        ),
                    ],
                )
            )

        return ft.Container(
            col={"sm": 12, "lg": 6},
            padding=20,
            border_radius=12,
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            content=ft.Column(
                spacing=8,
                controls=controls,
            ),
        )
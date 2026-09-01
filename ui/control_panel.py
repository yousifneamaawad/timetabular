"""
ui/control_panel.py

Modern Solver Control Panel
Compatible with Flet 0.85+
"""

from typing import TYPE_CHECKING

import flet as ft

if TYPE_CHECKING:
    from app import SchedulerApp


class ControlPanel:
    """Solver configuration and execution panel."""

    def __init__(self, app: "SchedulerApp"):
        self.app = app

        # ---------------------------------------------------------
        # Configuration Inputs
        # ---------------------------------------------------------

        self.slots_input = ft.TextField(
            label="Periods per Day",
            value=str(self.app.config.slots_per_day),
            width=180,
            keyboard_type=ft.KeyboardType.NUMBER,
            text_align=ft.TextAlign.CENTER,
        )

        self.days_input = ft.TextField(
            label="Days per Week",
            value=str(self.app.config.days_per_week),
            width=180,
            keyboard_type=ft.KeyboardType.NUMBER,
            text_align=ft.TextAlign.CENTER,
        )

        self.timeout_input = ft.TextField(
            label="Time Limit (seconds)",
            value=str(self.app.config.time_limit_seconds),
            width=180,
            keyboard_type=ft.KeyboardType.NUMBER,
            text_align=ft.TextAlign.CENTER,
        )

        self.same_day_switch = ft.Switch(
            label="Prevent Same-Day Lectures",
            value=self.app.config.prevent_same_day,
        )

        # ---------------------------------------------------------
        # Solver Controls
        # ---------------------------------------------------------

        self.solve_button = ft.FilledButton(
            text="Generate Schedule",
            icon=ft.Icons.PLAY_ARROW,
            height=46,
            on_click=self._on_solve_click,
        )

        self.cancel_button = ft.OutlinedButton(
            text="Cancel",
            icon=ft.Icons.STOP,
            height=46,
            visible=False,
            on_click=lambda e: self.app.cancel_solver(),
        )

        self.progress = ft.ProgressRing(
            visible=False,
            width=22,
            height=22,
            stroke_width=3,
        )

        self.status_text = ft.Text(
            "Ready",
            color=ft.Colors.GREY,
            size=13,
        )

        # ---------------------------------------------------------
        # Weight Fields
        # ---------------------------------------------------------

        self.weight_fields = {
            "Student Gaps": self._weight_field(
                self.app.weights.student_gaps
            ),
            "Teacher Gaps": self._weight_field(
                self.app.weights.teacher_gaps
            ),
            "Morning Preference": self._weight_field(
                self.app.weights.morning_preference
            ),
            "Evening Penalty": self._weight_field(
                self.app.weights.evening_penalty
            ),
            "Preferred Room": self._weight_field(
                self.app.weights.preferred_room
            ),
        }
        # ---------------------------------------------------------
        # Database Buttons
        # ---------------------------------------------------------

        self.generate_mock_button = ft.ElevatedButton(
            text="Generate Mock Data",
            icon=ft.Icons.DATA_ARRAY,
            on_click=self._generate_mock_data,
        )

        self.clear_schedule_button = ft.ElevatedButton(
            text="Clear Schedule",
            icon=ft.Icons.DELETE,
            style=ft.ButtonStyle(
                bgcolor=ft.Colors.RED,
                color=ft.Colors.WHITE,
            ),
            on_click=self._clear_schedule,
        )

    # =============================================================
    # Helper Widgets
    # =============================================================

    def _weight_field(self, value: int) -> ft.TextField:
        return ft.TextField(
            value=str(value),
            width=170,
            keyboard_type=ft.KeyboardType.NUMBER,
            text_align=ft.TextAlign.CENTER,
        )

    def _section_title(self, text: str):
        return ft.Text(
            text,
            size=18,
            weight=ft.FontWeight.BOLD,
        )

    def _card(self, title: str, controls: list[ft.Control]):

        return ft.Container(
            border_radius=12,
            padding=20,
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            content=ft.Column(
                spacing=15,
                controls=[
                    self._section_title(title),
                    *controls,
                ],
            ),
        )

    # =============================================================
    # Main UI
    # =============================================================

    def build(self):

        return ft.Column(
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=20,
            controls=[

                ft.Text(
                    "Settings & Solver",
                    size=30,
                    weight=ft.FontWeight.BOLD,
                ),

                ft.Text(
                    "Configure the optimization engine and generate schedules.",
                    color=ft.Colors.GREY,
                ),

                ft.Divider(),

                self._card(
                    "Schedule Parameters",
                    [

                        ft.ResponsiveRow(
                            controls=[

                                ft.Container(
                                    col={"sm":12,"md":4},
                                    content=self.slots_input,
                                ),

                                ft.Container(
                                    col={"sm":12,"md":4},
                                    content=self.days_input,
                                ),

                                ft.Container(
                                    col={"sm":12,"md":4},
                                    content=self.timeout_input,
                                ),

                            ]
                        ),

                        self.same_day_switch,

                    ],
                ),
                self._card(
                    "Solver Control",
                    [

                        ft.Row(
                            controls=[
                                self.solve_button,
                                self.cancel_button,
                                self.progress,
                            ],
                            spacing=15,
                        ),

                        self.status_text,

                    ],
                ),

                self._card(
                    "Objective Weights",
                    [

                        ft.Text(
                            "Higher values give higher priority during optimization.",
                            color=ft.Colors.GREY,
                            size=13,
                        ),

                        ft.ResponsiveRow(
                            controls=[

                                ft.Container(
                                    col={"sm":12,"md":6,"lg":4},
                                    content=ft.Column(
                                        controls=[
                                            ft.Text("Student Gaps"),
                                            self.weight_fields["Student Gaps"],
                                        ]
                                    ),
                                ),

                                ft.Container(
                                    col={"sm":12,"md":6,"lg":4},
                                    content=ft.Column(
                                        controls=[
                                            ft.Text("Teacher Gaps"),
                                            self.weight_fields["Teacher Gaps"],
                                        ]
                                    ),
                                ),

                                ft.Container(
                                    col={"sm":12,"md":6,"lg":4},
                                    content=ft.Column(
                                        controls=[
                                            ft.Text("Morning Preference"),
                                            self.weight_fields["Morning Preference"],
                                        ]
                                    ),
                                ),

                                ft.Container(
                                    col={"sm":12,"md":6,"lg":6},
                                    content=ft.Column(
                                        controls=[
                                            ft.Text("Evening Penalty"),
                                            self.weight_fields["Evening Penalty"],
                                        ]
                                    ),
                                ),

                                ft.Container(
                                    col={"sm":12,"md":6,"lg":6},
                                    content=ft.Column(
                                        controls=[
                                            ft.Text("Preferred Room"),
                                            self.weight_fields["Preferred Room"],
                                        ]
                                    ),
                                ),

                            ],
                            run_spacing=15,
                        ),

                    ],
                ),

                self._card(
                    "Database",
                    [

                        ft.Row(
                            controls=[
                                self.generate_mock_button,
                                self.clear_schedule_button,
                            ],
                            wrap=True,
                            spacing=15,
                        ),

                    ],
                ),

            ],
        )

    # =============================================================
    # Solver Actions
    # =============================================================

    def _update_weights(self):

        try:

            self.app.weights.student_gaps = int(
                self.weight_fields["Student Gaps"].value
            )

            self.app.weights.teacher_gaps = int(
                self.weight_fields["Teacher Gaps"].value
            )

            self.app.weights.morning_preference = int(
                self.weight_fields["Morning Preference"].value
            )

            self.app.weights.evening_penalty = int(
                self.weight_fields["Evening Penalty"].value
            )

            self.app.weights.preferred_room = int(
                self.weight_fields["Preferred Room"].value
            )

        except ValueError:
            pass
    def _on_solve_click(self, e):

        try:

            self.app.config.slots_per_day = int(self.slots_input.value)
            self.app.config.days_per_week = int(self.days_input.value)
            self.app.config.time_limit_seconds = float(self.timeout_input.value)
            self.app.config.prevent_same_day = self.same_day_switch.value

            self._update_weights()

        except ValueError:

            self.status_text.value = "Please enter valid numeric values."
            self.status_text.color = ft.Colors.RED
            self.app.page.update()
            return

        self.solve_button.visible = False
        self.cancel_button.visible = True
        self.progress.visible = True

        self.status_text.value = "Generating timetable..."
        self.status_text.color = ft.Colors.ORANGE

        self.app.page.update()

        self.app.run_solver()

        # Current app.py doesn't notify this panel when finished,
        # so reset immediately like the original implementation.
        self._reset_ui()

    def _reset_ui(self):

        self.solve_button.visible = True
        self.cancel_button.visible = False
        self.progress.visible = False

        self.status_text.value = "Ready"
        self.status_text.color = ft.Colors.GREY

        self.app.page.update()

    # =============================================================
    # Database Actions
    # =============================================================

    def _generate_mock_data(self, e):

        try:

            from generate_mock_data import generate_all_mock_data

            generate_all_mock_data()

            self.status_text.value = "Mock data generated successfully."
            self.status_text.color = ft.Colors.GREEN

        except Exception as ex:

            self.status_text.value = f"Error: {ex}"
            self.status_text.color = ft.Colors.RED

        self.app.page.update()

    def _clear_schedule(self, e):

        try:

            from database import db_manager

            with db_manager.get_connection() as conn:
                conn.execute("DELETE FROM schedule")
                conn.commit()

            self.status_text.value = "Schedule cleared."
            self.status_text.color = ft.Colors.GREEN

        except Exception as ex:

            self.status_text.value = f"Error: {ex}"
            self.status_text.color = ft.Colors.RED

        self.app.page.update()
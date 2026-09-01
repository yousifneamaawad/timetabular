# ui/dialogs.py
"""
Dialog components for the scheduler application.
"""

import flet as ft
from pathlib import Path
import webbrowser


class ExportDialog:
    """Dialog shown after successful export."""
    
    def __init__(self, page: ft.Page, filepath: str):
        self.page = page
        self.filepath = filepath
        self.filepath_obj = Path(filepath)
    
    def show(self):
        """Show the export success dialog."""
        def close_dialog(e):
            self.dialog.open = False
            self.page.update()
        
        def open_file(e):
            """Open the exported file with default application."""
            webbrowser.open(str(self.filepath_obj.absolute()))
        
        def open_folder(e):
            """Open the folder containing the exported file."""
            webbrowser.open(str(self.filepath_obj.parent.absolute()))
        
        self.dialog = ft.AlertDialog(
            modal=True,
            title=ft.Row([
                ft.Icon(ft.Icons.CHECK_CIRCLE, color=ft.Colors.GREEN_400, size=28),
                ft.Text("Export Successful", size=20, weight=ft.FontWeight.BOLD),
            ], spacing=12),
            content=ft.Column([
                ft.Text(f"File saved successfully:", size=14),
                ft.Container(
                    content=ft.Text(
                        self.filepath_obj.name,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.BLUE_200,
                        size=14,
                    ),
                    padding=ft.padding.symmetric(vertical=8),
                ),
                ft.Text(
                    f"Location: {self.filepath_obj.parent}",
                    size=12,
                    color=ft.Colors.GREY_400,
                ),
                ft.Text(
                    f"Size: {self._get_file_size()}",
                    size=12,
                    color=ft.Colors.GREY_400,
                ),
            ], spacing=8, tight=True),
            actions=[
                ft.TextButton(
                    "Open File",
                    icon=ft.Icons.OPEN_IN_NEW,
                    on_click=open_file,
                ),
                ft.TextButton(
                    "Open Folder",
                    icon=ft.Icons.FOLDER_OPEN,
                    on_click=open_folder,
                ),
                ft.ElevatedButton(
                    "Close",
                    icon=ft.Icons.CLOSE,
                    on_click=close_dialog,
                    style=ft.ButtonStyle(
                        bgcolor=ft.Colors.BLUE_800,
                        color=ft.Colors.WHITE,
                    ),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        
        self.page.dialog = self.dialog
        self.dialog.open = True
        self.page.update()
    
    def _get_file_size(self) -> str:
        """Get human-readable file size."""
        try:
            size = self.filepath_obj.stat().st_size
            for unit in ['B', 'KB', 'MB', 'GB']:
                if size < 1024.0:
                    return f"{size:.1f} {unit}"
                size /= 1024.0
            return f"{size:.1f} TB"
        except Exception:
            return "Unknown"


class ConfirmDialog:
    """Confirmation dialog for destructive actions."""
    
    def __init__(
        self, 
        page: ft.Page, 
        title: str, 
        message: str, 
        on_confirm: callable = None,
        on_cancel: callable = None,
        confirm_text: str = "Confirm",
        cancel_text: str = "Cancel",
        is_dangerous: bool = False,
    ):
        self.page = page
        self.title = title
        self.message = message
        self.on_confirm = on_confirm
        self.on_cancel = on_cancel
        self.confirm_text = confirm_text
        self.cancel_text = cancel_text
        self.is_dangerous = is_dangerous
    
    def show(self):
        """Show the confirmation dialog."""
        def handle_confirm(e):
            self.dialog.open = False
            self.page.update()
            if self.on_confirm:
                self.on_confirm()
        
        def handle_cancel(e):
            self.dialog.open = False
            self.page.update()
            if self.on_cancel:
                self.on_cancel()
        
        confirm_button_style = ft.ButtonStyle(
            bgcolor=ft.Colors.RED_700 if self.is_dangerous else ft.Colors.BLUE_800,
            color=ft.Colors.WHITE,
        )
        
        self.dialog = ft.AlertDialog(
            modal=True,
            title=ft.Row([
                ft.Icon(
                    ft.Icons.WARNING_AMBER if self.is_dangerous else ft.Icons.INFO,
                    color=ft.Colors.RED_400 if self.is_dangerous else ft.Colors.BLUE_400,
                    size=28,
                ),
                ft.Text(self.title, size=20, weight=ft.FontWeight.BOLD),
            ], spacing=12),
            content=ft.Text(self.message, size=14),
            actions=[
                ft.TextButton(
                    self.cancel_text,
                    icon=ft.Icons.CANCEL,
                    on_click=handle_cancel,
                ),
                ft.ElevatedButton(
                    self.confirm_text,
                    icon=ft.Icons.CHECK if not self.is_dangerous else ft.Icons.DELETE,
                    on_click=handle_confirm,
                    style=confirm_button_style,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        
        self.page.dialog = self.dialog
        self.dialog.open = True
        self.page.update()


class SettingsDialog:
    """Dialog for advanced solver settings."""
    
    def __init__(self, page: ft.Page, config: dict = None):
        self.page = page
        self.config = config or {}
    
    def show(self):
        """Show the settings dialog."""
        def close_dialog(e):
            self.dialog.open = False
            self.page.update()
        
        def save_settings(e):
            # Save settings logic here
            self.dialog.open = False
            self.page.update()
        
        self.dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Advanced Settings", size=20, weight=ft.FontWeight.BOLD),
            content=ft.Column([
                ft.TextField(
                    label="Number of Search Workers",
                    value="8",
                    keyboard_type=ft.KeyboardType.NUMBER,
                    width=200,
                ),
                ft.TextField(
                    label="Random Seed",
                    value="42",
                    keyboard_type=ft.KeyboardType.NUMBER,
                    width=200,
                ),
                ft.Switch(label="Log Search Progress", value=True),
                ft.Switch(label="Use Parallel Search", value=True),
                ft.Switch(label="Enable Symmetry Breaking", value=True),
            ], spacing=12, height=250, scroll=ft.ScrollMode.AUTO),
            actions=[
                ft.TextButton("Cancel", on_click=close_dialog),
                ft.ElevatedButton(
                    "Save Settings",
                    icon=ft.Icons.SAVE,
                    on_click=save_settings,
                    style=ft.ButtonStyle(
                        bgcolor=ft.Colors.BLUE_800,
                        color=ft.Colors.WHITE,
                    ),
                ),
            ],
        )
        
        self.page.dialog = self.dialog
        self.dialog.open = True
        self.page.update()


class ErrorDialog:
    """Dialog for displaying errors."""
    
    @staticmethod
    def show(page: ft.Page, title: str, message: str):
        """Show an error dialog."""
        def close(e):
            dialog.open = False
            page.update()
        
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Row([
                ft.Icon(ft.Icons.ERROR, color=ft.Colors.RED_400, size=28),
                ft.Text(title, size=20, weight=ft.FontWeight.BOLD),
            ], spacing=12),
            content=ft.Text(message, size=14),
            actions=[
                ft.ElevatedButton(
                    "OK",
                    icon=ft.Icons.CHECK,
                    on_click=close,
                    style=ft.ButtonStyle(
                        bgcolor=ft.Colors.RED_700,
                        color=ft.Colors.WHITE,
                    ),
                ),
            ],
        )
        
        page.dialog = dialog
        dialog.open = True
        page.update()


class ProgressDialog:
    """Dialog showing solver progress."""
    
    def __init__(self, page: ft.Page):
        self.page = page
        self.progress_bar = ft.ProgressBar(width=400)
        self.status_text = ft.Text("Initializing...", size=14)
        self.time_text = ft.Text("", size=12, color=ft.Colors.GREY_400)
        self.solutions_text = ft.Text("", size=12, color=ft.Colors.GREY_400)
    
    def show(self):
        """Show the progress dialog."""
        def cancel(e):
            self.dialog.open = False
            self.page.update()
        
        self.dialog = ft.AlertDialog(
            modal=True,
            title=ft.Row([
                ft.ProgressRing(width=20, height=20, stroke_width=2),
                ft.Text("Optimizing Schedule", size=20, weight=ft.FontWeight.BOLD),
            ], spacing=12),
            content=ft.Column([
                self.progress_bar,
                ft.Divider(height=16, color=ft.Colors.TRANSPARENT),
                self.status_text,
                self.time_text,
                self.solutions_text,
            ], spacing=8),
            actions=[
                ft.TextButton(
                    "Cancel",
                    icon=ft.Icons.STOP,
                    on_click=cancel,
                    style=ft.ButtonStyle(color=ft.Colors.RED_400),
                ),
            ],
        )
        
        self.page.dialog = self.dialog
        self.dialog.open = True
        self.page.update()
    
    def update_progress(self, status: str, elapsed: float, solutions: int):
        """Update the progress dialog."""
        self.status_text.value = status
        self.time_text.value = f"Time elapsed: {elapsed:.1f}s"
        self.solutions_text.value = f"Solutions found: {solutions}"
        self.page.update()
    
    def close(self):
        """Close the progress dialog."""
        if self.dialog:
            self.dialog.open = False
            self.page.update()
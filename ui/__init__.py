# ui/__init__.py
"""
UI package for the University Timetable Scheduler.
Contains all user interface components.
"""

from .dashboard import DashboardView
from .timetable_grid import TimetableView
from .control_panel import ControlPanel
from .dialogs import ExportDialog, ConfirmDialog, SettingsDialog, ErrorDialog
from .reports import ReportsView

__all__ = [
    'DashboardView',
    'TimetableView', 
    'ControlPanel',
    'ExportDialog',
    'ConfirmDialog',
    'SettingsDialog',
    'ErrorDialog',
    'ReportsView',
]
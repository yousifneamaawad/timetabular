"""
utils.py

Shared utilities for the Scheduler Debugger.

This module intentionally contains NO scheduler-specific logic.
Everything here is reusable by every checker.

Author: ChatGPT
"""

from __future__ import annotations

import os
import sys
import time
import json
import shutil
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, Optional

# =============================================================================
# Paths
# =============================================================================

ROOT = Path(__file__).resolve().parent
REPORT_DIR = ROOT / "reports"

REPORT_DIR.mkdir(exist_ok=True)

# =============================================================================
# Terminal Colors
# =============================================================================


class Color:
    RESET = "\033[0m"

    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    BOLD = "\033[1m"

    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"


# Disable colors on Windows terminals that don't support ANSI.

if os.name == "nt":
    os.system("")


# =============================================================================
# Icons
# =============================================================================


class Icon:
    PASS = "✓"
    FAIL = "✗"
    WARN = "!"
    INFO = "•"


# =============================================================================
# Timing
# =============================================================================


class Timer:
    def __init__(self):
        self.start = time.perf_counter()

    @property
    def elapsed(self):
        return time.perf_counter() - self.start


# =============================================================================
# Logging
# =============================================================================


@dataclass
class LogEntry:
    level: str
    message: str
    timestamp: float = field(default_factory=time.time)


class Logger:

    def __init__(self):
        self.entries: list[LogEntry] = []

    def info(self, msg):
        self.entries.append(LogEntry("INFO", msg))
        print(f"{Color.CYAN}{Icon.INFO}{Color.RESET} {msg}")

    def success(self, msg):
        self.entries.append(LogEntry("PASS", msg))
        print(f"{Color.GREEN}{Icon.PASS}{Color.RESET} {msg}")

    def warning(self, msg):
        self.entries.append(LogEntry("WARN", msg))
        print(f"{Color.YELLOW}{Icon.WARN}{Color.RESET} {msg}")

    def error(self, msg):
        self.entries.append(LogEntry("FAIL", msg))
        print(f"{Color.RED}{Icon.FAIL}{Color.RESET} {msg}")

    def export_json(self, filename="audit_log.json"):
        path = REPORT_DIR / filename
        with open(path, "w", encoding="utf8") as f:
            json.dump(
                [
                    {
                        "time": e.timestamp,
                        "level": e.level,
                        "message": e.message,
                    }
                    for e in self.entries
                ],
                f,
                indent=4,
            )


logger = Logger()

# =============================================================================
# Sections
# =============================================================================


def title(text: str):

    width = shutil.get_terminal_size((120, 30)).columns

    print()
    print("=" * width)
    print(text.center(width))
    print("=" * width)


def section(text: str):
    print()
    print(Color.BOLD + text + Color.RESET)
    print("-" * len(text))


# =============================================================================
# Formatting
# =============================================================================


def yes_no(value: bool):
    return f"{Icon.PASS}" if value else f"{Icon.FAIL}"


def human_int(value: int):
    return f"{value:,}"


def percent(part, whole):

    if whole == 0:
        return "0%"

    return f"{100 * part / whole:.1f}%"


def plural(n, singular, plural_word=None):
    if n == 1:
        return singular
    return plural_word or singular + "s"


# =============================================================================
# Tables
# =============================================================================


def print_table(rows):

    if not rows:
        return

    widths = [
        max(len(str(row[i])) for row in rows)
        for i in range(len(rows[0]))
    ]

    for row in rows:

        line = []

        for w, value in zip(widths, row):
            line.append(str(value).ljust(w))

        print(" | ".join(line))


# =============================================================================
# Report
# =============================================================================


class Report:

    def __init__(self):
        self.lines = []

    def add(self, text=""):
        self.lines.append(text)

    def heading(self, text):
        self.lines.append("")
        self.lines.append(text)
        self.lines.append("=" * len(text))

    def save(self, filename="report.txt"):

        path = REPORT_DIR / filename

        with open(path, "w", encoding="utf8") as f:
            f.write("\n".join(self.lines))

        logger.success(f"Report written to {path}")


# =============================================================================
# Assertions
# =============================================================================


def require(condition, message):

    if not condition:
        raise RuntimeError(message)


# =============================================================================
# Safe attribute access
# =============================================================================


def safe_get(obj, attr, default=None):
    return getattr(obj, attr, default)


# =============================================================================
# Statistics
# =============================================================================


@dataclass
class Counter:

    values: dict[str, int] = field(default_factory=dict)

    def add(self, key, amount=1):
        self.values[key] = self.values.get(key, 0) + amount

    def get(self, key):
        return self.values.get(key, 0)

    def dump(self):

        rows = [["Item", "Count"]]

        for k in sorted(self.values):
            rows.append([k, human_int(self.values[k])])

        print_table(rows)


# =============================================================================
# Banner
# =============================================================================


def banner():

    title("UNIVERSITY SCHEDULER DEBUGGER")

    print(
        f"""
Timestamp : {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
Python    : {sys.version.split()[0]}
Platform  : {sys.platform}
Reports   : {REPORT_DIR}
"""
    )


# =============================================================================
# Compatibility layer
# =============================================================================

class Statistics(Counter):
    """
    Backward-compatible wrapper around Counter.

    Older debugger modules expect a Statistics class with
    add(), get(), and print() methods.
    """

    def print(self):
        print()
        print("Statistics")
        print("----------")
        self.dump()


class ReportWriter:
    """
    Simple static report writer expected by the debugger modules.
    """

    @staticmethod
    def write(filename: str, lines):
        if isinstance(lines, str):
            lines = [lines]

        path = REPORT_DIR / filename

        with open(path, "w", encoding="utf8") as f:
            f.write("\n".join(str(x) for x in lines))

        logger.success(f"Report written to {path}")

        return path


def banner(text: str = "UNIVERSITY SCHEDULER DEBUGGER"):
    """
    Improved banner that is backward-compatible.

    Supports both:
        banner()
        banner("DATABASE CHECK")
    """

    title(text)

    print(
        f"""
Timestamp : {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
Python    : {sys.version.split()[0]}
Platform  : {sys.platform}
Reports   : {REPORT_DIR}
"""
    )
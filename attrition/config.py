"""Shared settings for the attrition / retention analysis.

Every definition used on the dashboard lives here so the numbers can be traced
back to one place. Dates are local (America/Chicago) calendar dates.
"""
from __future__ import annotations

import datetime as dt
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("ATTRITION_DATA", ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"             # untouched API pages (gitignored, contains PII)
TIDY_DIR = DATA_DIR / "tidy"           # one CSV per table (gitignored, contains PII)
OUT_DIR = Path(os.environ.get("ATTRITION_OUT", ROOT / "out"))  # dashboard + metrics
PRIVATE_DIR = OUT_DIR / "private"      # at-risk list with names (gitignored)

TZ = "America/Chicago"

# "Today" for the analysis. Override with AS_OF=YYYY-MM-DD for reproducible reruns.
AS_OF = dt.date.fromisoformat(os.environ.get("AS_OF", dt.date.today().isoformat()))

# How far back to pull activity. Earlier history is only used to decide whether
# someone is truly a first-time guest and to compute tenure.
HISTORY_START = dt.date.fromisoformat(os.environ.get("HISTORY_START", "2023-01-01"))

# ---- Definitions -----------------------------------------------------------
# Regular attender: 2+ attendances per month on average over a 3-month window
# = at least 6 distinct attendance days in a 91-day window.
REGULAR_WINDOW_DAYS = 91
REGULAR_MIN_DAYS = 6

# Lapsed: regular in the baseline window (the 91 days ending one year before
# AS_OF) and NO activity of any kind in the last 90 days.
LAPSE_QUIET_DAYS = 90

# Giving "regularly": a gift in at least 2 of the 3 months of the window.
GIVING_MIN_MONTHS = 2

# At-risk: regular in the 91 days before the recent window, and attendance in
# the most recent AT_RISK_RECENT_DAYS days fell by at least AT_RISK_DROP.
AT_RISK_RECENT_DAYS = 90
AT_RISK_DROP = 0.5

# A first-time guest must have no recorded activity before their first visit
# and a People record created no earlier than this many days before it
# (guards against long-time people who simply never checked in before).
NEW_PERSON_GRACE_DAYS = 60

# Days of history required before a first visit before we call someone "new".
NEWCOMER_LOOKBACK_DAYS = int(os.environ.get("NEWCOMER_LOOKBACK_DAYS", "183"))

HEALTHY_ATTRITION = (0.10, 0.15)


def windows(as_of: dt.date = AS_OF) -> dict[str, tuple[dt.date, dt.date]]:
    """Inclusive (start, end) windows used throughout the analysis."""
    one_year_ago = as_of - dt.timedelta(days=365)
    d = dt.timedelta
    return {
        "baseline": (one_year_ago - d(days=REGULAR_WINDOW_DAYS - 1), one_year_ago),
        "recent_quiet": (as_of - d(days=LAPSE_QUIET_DAYS - 1), as_of),
        "current": (as_of - d(days=REGULAR_WINDOW_DAYS - 1), as_of),
        "newcomer": (one_year_ago + d(days=1), as_of),
        "at_risk_prior": (
            as_of - d(days=AT_RISK_RECENT_DAYS + REGULAR_WINDOW_DAYS - 1),
            as_of - d(days=AT_RISK_RECENT_DAYS),
        ),
        "at_risk_recent": (as_of - d(days=AT_RISK_RECENT_DAYS - 1), as_of),
    }


# ---- Ministry area ---------------------------------------------------------
# Check-Ins event names -> ministry area. First matching rule wins. Anything
# unmatched is reported on the dashboard's data-gaps panel so it can be fixed.
EVENT_RULES: list[tuple[str, str]] = [
    (r"dream team|serve day|all assignments|admin|prayer team|rehearsal", "serving"),
    (r"test|practice|tester", "ignore"),
    # One-off events that draw many people from outside the church: they count as
    # activity (so the person is not "lapsed") but not as attendance days or first visits.
    (r"conference|summer blast|childcare|one night|men's night|\bxo\b|make waves|radiant|friendsgiving", "special"),
    (r"kids", "kids"),
    (r"student|middle school|motion", "students"),
    (r"\bcy\b|cya|young adult", "cya"),
]
DEFAULT_EVENT_AREA = "adults"


def event_area(name: str) -> str:
    n = (name or "").strip().lower()
    for pattern, area in EVENT_RULES:
        if re.search(pattern, n):
            return area
    return DEFAULT_EVENT_AREA


AGE_BANDS = [
    (0, 11, "Kids (0-10)"),
    (11, 18, "Students (11-17)"),
    (18, 30, "18-29"),
    (30, 45, "30-44"),
    (45, 65, "45-64"),
    (65, 200, "65+"),
]


def age_band(age: float | None) -> str:
    if age is None or age != age:  # NaN
        return "Unknown"
    for lo, hi, label in AGE_BANDS:
        if lo <= age < hi:
            return label
    return "Unknown"

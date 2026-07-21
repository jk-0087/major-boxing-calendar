from __future__ import annotations

import re
from datetime import date, datetime
from typing import Iterable

import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from scripts.models import DiscoveredEvent

DAZN_SCHEDULE_URL = (
    "https://www.dazn.com/en-US/news/boxing/"
    "boxing-schedule-fight-dates-tv-channel-and-live-stream-for-confirmed-cards/"
    "1l3zwnho1gotu17qp8l44fmww9"
)

MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|November|December|"
    "Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
)
DATE_RE = re.compile(rf"\b(?:{MONTHS})\s+\d{{1,2}}(?:,\s*\d{{4}})?\b", re.I)
FIGHT_RE = re.compile(
    r"(?P<a>[A-ZÀ-ÖØ-öø-ÿ][\wÀ-ÖØ-öø-ÿ.'’\- ]{1,50})\s+v(?:s\.?|\.)\s+"
    r"(?P<b>[A-ZÀ-ÖØ-öø-ÿ][\wÀ-ÖØ-öø-ÿ.'’\- ]{1,50})",
    re.I,
)

class DaznSourceError(RuntimeError):
    pass

def _normalise_name(value: str) -> str:
    return " ".join(value.strip(" -–—:;,.\t").split())

def _parse_date(text: str, today: date) -> date | None:
    match = DATE_RE.search(text)
    if not match:
        return None
    raw = match.group(0)
    if not re.search(r"\b\d{4}\b", raw):
        raw = f"{raw}, {today.year}"
    parsed = date_parser.parse(raw, fuzzy=False).date()
    # Schedule pages often roll into next year near year-end.
    if parsed < today and (today - parsed).days > 180 and str(today.year) not in match.group(0):
        parsed = parsed.replace(year=today.year + 1)
    return parsed

def fetch_dazn_events(today: date | None = None) -> list[DiscoveredEvent]:
    today = today or date.today()
    try:
        response = requests.get(
            DAZN_SCHEDULE_URL,
            timeout=30,
            headers={
                "User-Agent": "MajorBoxingCalendar/1.0 (+https://jk-0087.github.io/major-boxing-calendar/)"
            },
        )
    except requests.RequestException as exc:
        raise DaznSourceError(f"Unable to fetch DAZN schedule: {exc}") from exc
    if response.status_code != 200:
        raise DaznSourceError(f"DAZN returned HTTP {response.status_code}")

    soup = BeautifulSoup(response.text, "html.parser")
    lines = [" ".join(x.split()) for x in soup.get_text("\n").splitlines() if x.strip()]
    found: dict[tuple[str, date], DiscoveredEvent] = {}
    current_date: date | None = None

    for line in lines:
        parsed_date = _parse_date(line, today)
        if parsed_date:
            current_date = parsed_date
        for fight in FIGHT_RE.finditer(line):
            if not current_date:
                continue
            left = _normalise_name(fight.group("a"))
            right = _normalise_name(fight.group("b"))
            # Avoid headings or sentence fragments that are clearly too long.
            if len(left.split()) > 7 or len(right.split()) > 7:
                continue
            title = f"{left} vs {right}"
            event = DiscoveredEvent(title, current_date, DAZN_SCHEDULE_URL)
            found[(title.casefold(), current_date)] = event

    events = sorted(found.values(), key=lambda event: (event.event_date, event.title))
    if len(events) < 3:
        raise DaznSourceError(
            f"Safety stop: expected at least 3 DAZN schedule entries, parsed {len(events)}"
        )
    return events

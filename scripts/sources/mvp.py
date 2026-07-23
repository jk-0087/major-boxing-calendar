from __future__ import annotations

import re
from datetime import date

import requests
from bs4 import BeautifulSoup

from scripts.models import DiscoveredEvent
from scripts.sources.official import FIGHT_RE, _clean, _parse_date

MVP_EVENTS_URL = "https://www.mostvaluablepromotions.com/events/"
MVP_PREFIX_RE = re.compile(r"^MVPW\s*\d+\s*[-–—:]\s*", re.I)


class MvpSourceError(RuntimeError):
    pass


def _fight_title(line: str) -> str | None:
    cleaned = MVP_PREFIX_RE.sub("", _clean(line))
    fight = FIGHT_RE.fullmatch(cleaned) or FIGHT_RE.search(cleaned)
    if not fight:
        return None
    left = _clean(fight.group("a"))
    right = _clean(fight.group("b"))
    if not left or not right:
        return None
    return f"{left} vs {right}"


def parse_mvp_schedule(html: str, today: date) -> list[DiscoveredEvent]:
    soup = BeautifulSoup(html, "html.parser")
    lines = [_clean(line) for line in soup.get_text("\n").splitlines() if _clean(line)]
    pending_title: str | None = None
    found: dict[tuple[str, date], DiscoveredEvent] = {}

    for line in lines:
        title = _fight_title(line)
        if title:
            pending_title = title
            continue

        event_date = _parse_date(line, today)
        if pending_title and event_date:
            if event_date >= today:
                found[(pending_title.casefold(), event_date)] = DiscoveredEvent(
                    pending_title,
                    event_date,
                    MVP_EVENTS_URL,
                )
            pending_title = None

    return sorted(found.values(), key=lambda event: (event.event_date, event.title))


def fetch_mvp_events(today: date | None = None) -> list[DiscoveredEvent]:
    today = today or date.today()
    try:
        response = requests.get(
            MVP_EVENTS_URL,
            timeout=30,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "Chrome/126.0 Safari/537.36 MajorBoxingCalendar/1.0"
                ),
                "Accept-Language": "en-AU,en;q=0.9",
            },
        )
    except requests.RequestException as exc:
        raise MvpSourceError(f"Unable to fetch MVP: {exc}") from exc
    if response.status_code != 200:
        raise MvpSourceError(f"MVP returned HTTP {response.status_code}")

    events = parse_mvp_schedule(response.text, today)
    if not events:
        raise MvpSourceError("Safety stop: MVP parsed 0 upcoming schedule entries")
    return events

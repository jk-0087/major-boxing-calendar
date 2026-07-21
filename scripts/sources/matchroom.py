from __future__ import annotations

import re
from datetime import date, datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from scripts.models import DiscoveredEvent

MATCHROOM_EVENTS_URL = "https://www.matchroomboxing.com/events/"

DATE_RE = re.compile(
    r"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)(?:day)?\s+"
    r"(?P<day>\d{1,2})\s+"
    r"(?P<month>Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"(?:\s+(?P<year>\d{4}))?\b",
    re.I,
)
SHORT_DATE_RE = re.compile(
    r"\b(?P<day>\d{1,2})\s+"
    r"(?P<month>Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"(?:\s+(?P<year>\d{4}))?\b",
    re.I,
)
FIGHT_RE = re.compile(
    r"(?P<a>[A-ZÀ-ÖØ-öø-ÿ][\wÀ-ÖØ-öø-ÿ.'’\- ]{1,55}?)\s+"
    r"v(?:s\.?|\.)\s+"
    r"(?P<b>[A-ZÀ-ÖØ-öø-ÿ][\wÀ-ÖØ-öø-ÿ.'’\- ]{1,55})",
    re.I,
)


class MatchroomSourceError(RuntimeError):
    pass


def _clean(value: str) -> str:
    return " ".join(value.strip(" -–—:;,。\t\n").split())


def _parse_date(text: str, today: date) -> date | None:
    match = DATE_RE.search(text) or SHORT_DATE_RE.search(text)
    if not match:
        return None
    year = int(match.group("year")) if match.group("year") else today.year
    parsed = date_parser.parse(
        f"{match.group('day')} {match.group('month')} {year}",
        dayfirst=True,
        fuzzy=False,
    ).date()
    # During late-year rollover, an undated January/February card belongs to next year.
    if not match.group("year") and parsed < today and (today - parsed).days > 120:
        parsed = parsed.replace(year=today.year + 1)
    return parsed


def _extract_from_block(text: str, href: str, today: date) -> DiscoveredEvent | None:
    event_date = _parse_date(text, today)
    fight = FIGHT_RE.search(text)
    if not event_date or not fight:
        return None
    left = _clean(fight.group("a"))
    right = _clean(fight.group("b"))
    if not left or not right or len(left.split()) > 7 or len(right.split()) > 7:
        return None
    return DiscoveredEvent(f"{left} vs {right}", event_date, href)


def fetch_matchroom_events(today: date | None = None) -> list[DiscoveredEvent]:
    today = today or date.today()
    try:
        response = requests.get(
            MATCHROOM_EVENTS_URL,
            timeout=30,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "Chrome/126.0 Safari/537.36 MajorBoxingCalendar/1.0"
                ),
                "Accept-Language": "en-GB,en;q=0.9",
            },
        )
    except requests.RequestException as exc:
        raise MatchroomSourceError(f"Unable to fetch Matchroom schedule: {exc}") from exc
    if response.status_code != 200:
        raise MatchroomSourceError(f"Matchroom returned HTTP {response.status_code}")

    soup = BeautifulSoup(response.text, "html.parser")
    found: dict[tuple[str, date], DiscoveredEvent] = {}

    # Prefer event links and their enclosing card text. This is resilient to CSS-class changes.
    for anchor in soup.select('a[href*="/events/"]'):
        href = urljoin(MATCHROOM_EVENTS_URL, anchor.get("href", ""))
        if href.rstrip("/") == MATCHROOM_EVENTS_URL.rstrip("/"):
            continue
        anchor_text = _clean(anchor.get_text(" ", strip=True))
        fight = FIGHT_RE.fullmatch(anchor_text) or FIGHT_RE.search(anchor_text)
        if not fight:
            continue
        left = _clean(fight.group("a"))
        right = _clean(fight.group("b"))
        if not left or not right or len(left.split()) > 7 or len(right.split()) > 7:
            continue
        parent = anchor
        event_date = None
        for _ in range(5):
            text = _clean(parent.get_text(" ", strip=True))
            event_date = _parse_date(text, today)
            if event_date:
                break
            parent = parent.parent
            if parent is None:
                break
        if event_date:
            event = DiscoveredEvent(f"{left} vs {right}", event_date, href)
            found[(event.title.casefold(), event.event_date)] = event

    # Fallback for layouts where the event title is not wrapped by the event link.
    if len(found) < 2:
        lines = [_clean(x) for x in soup.get_text("\n").splitlines() if x.strip()]
        current_date: date | None = None
        for line in lines:
            parsed = _parse_date(line, today)
            if parsed:
                current_date = parsed
            fight = FIGHT_RE.search(line)
            if current_date and fight:
                left, right = _clean(fight.group("a")), _clean(fight.group("b"))
                if left and right and len(left.split()) <= 7 and len(right.split()) <= 7:
                    title = f"{left} vs {right}"
                    found[(title.casefold(), current_date)] = DiscoveredEvent(
                        title, current_date, MATCHROOM_EVENTS_URL
                    )

    events = sorted(found.values(), key=lambda event: (event.event_date, event.title))
    if len(events) < 2:
        raise MatchroomSourceError(
            f"Safety stop: expected at least 2 Matchroom schedule entries, parsed {len(events)}"
        )
    return events

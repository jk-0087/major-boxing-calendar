from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from scripts.models import DiscoveredEvent


@dataclass(frozen=True)
class SourceSpec:
    name: str
    url: str


OFFICIAL_SOURCES = (
    SourceSpec("Queensberry", "https://queensberry.co.uk/"),
    SourceSpec("Top Rank", "https://toprank.com/events"),
    SourceSpec("The Ring / Riyadh Season", "https://www.ringmagazine.com/"),
    SourceSpec("Premier Boxing Champions", "https://www.premierboxingchampions.com/boxing-schedule"),
    SourceSpec("Golden Boy", "https://www.goldenboy.com/"),
    SourceSpec("BOXXER", "https://www.boxxer.com/"),
    SourceSpec("Most Valuable Promotions", "https://www.mostvaluablepromotions.com/events/"),
    SourceSpec("No Limit Boxing", "https://nolimitboxing.com.au/events"),
    SourceSpec("Tasman Fighters", "https://www.tasmanfighters.com/event-list"),
    SourceSpec("Zuffa Boxing", "https://www.ufc.com/zuffaboxing"),
)

MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|November|December|"
    "Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
)
DATE_RE = re.compile(
    rf"\b(?:(?:{MONTHS})\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,)?(?:\s+\d{{4}})?|"
    rf"\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{MONTHS})(?:\s+\d{{4}})?)\b",
    re.I,
)
FIGHT_RE = re.compile(
    r"(?P<a>[A-ZÀ-ÖØ-öø-ÿ][\wÀ-ÖØ-öø-ÿ.'’\- ]{1,55}?)\s+"
    r"(?:v(?:s\.?|\.)|versus)\s+"
    r"(?P<b>[A-ZÀ-ÖØ-öø-ÿ][\wÀ-ÖØ-öø-ÿ.'’\- ]{1,55})",
    re.I,
)


class OfficialSourceError(RuntimeError):
    pass


def _clean(value: str) -> str:
    return " ".join(value.strip(" -–—:;,.\t\n").split())


def _parse_date(value: str, today: date) -> date | None:
    match = DATE_RE.search(value)
    if not match:
        return None
    raw = re.sub(r"(?<=\d)(?:st|nd|rd|th)\b", "", match.group(0), flags=re.I)
    if not re.search(r"\b\d{4}\b", raw):
        raw = f"{raw} {today.year}"
    try:
        parsed = date_parser.parse(raw, fuzzy=False, dayfirst=raw[0].isdigit()).date()
    except (ValueError, OverflowError):
        return None
    if parsed < today and (today - parsed).days > 150 and str(today.year) not in match.group(0):
        parsed = parsed.replace(year=today.year + 1)
    return parsed


def parse_official_schedule(html: str, spec: SourceSpec, today: date) -> list[DiscoveredEvent]:
    soup = BeautifulSoup(html, "html.parser")
    lines = [_clean(line) for line in soup.get_text("\n").splitlines() if _clean(line)]
    found: dict[tuple[str, date], DiscoveredEvent] = {}
    current_date: date | None = None

    for index, line in enumerate(lines):
        parsed = _parse_date(line, today)
        if parsed:
            current_date = parsed
        if not current_date:
            continue

        fight = FIGHT_RE.fullmatch(line) or FIGHT_RE.search(line)
        if fight:
            left = _clean(fight.group("a"))
            right = _clean(fight.group("b"))
        elif line.casefold().rstrip(".") in {"v", "vs", "versus"} and 0 < index < len(lines) - 1:
            left = _clean(lines[index - 1])
            right = _clean(lines[index + 1])
        else:
            continue

        if not left or not right or len(left.split()) > 7 or len(right.split()) > 7:
            continue
        if _parse_date(left, today) or _parse_date(right, today):
            continue
        title = f"{left} vs {right}"
        found[(title.casefold(), current_date)] = DiscoveredEvent(title, current_date, spec.url)

    return sorted(found.values(), key=lambda event: (event.event_date, event.title))


def fetch_official_events(spec: SourceSpec, today: date | None = None) -> list[DiscoveredEvent]:
    today = today or date.today()
    try:
        response = requests.get(
            spec.url,
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
        raise OfficialSourceError(f"Unable to fetch {spec.name}: {exc}") from exc
    if response.status_code != 200:
        raise OfficialSourceError(f"{spec.name} returned HTTP {response.status_code}")

    events = parse_official_schedule(response.text, spec, today)
    if not events:
        raise OfficialSourceError(f"Safety stop: {spec.name} parsed 0 schedule entries")
    return events

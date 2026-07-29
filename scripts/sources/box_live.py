from __future__ import annotations

import re
from datetime import date

import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from scripts.models import DiscoveredEvent


BOX_LIVE_FEED_URL = "https://box.live/external-feeds/28633-2/"
BOX_LIVE_MIN_EVENTS = 8


class BoxLiveSourceError(RuntimeError):
    pass


def _event_date(value: str) -> date | None:
    cleaned = re.sub(r"(?<=\d)(?:st|nd|rd|th)\b", "", value, flags=re.I)
    try:
        return date_parser.parse(cleaned, fuzzy=False).date()
    except (ValueError, OverflowError):
        return None


def _title(value: str) -> str | None:
    match = re.fullmatch(r"\s*(.+?)\s+vs\.?\s+(.+?)\s*", value, flags=re.I)
    if not match:
        return None
    left = " ".join(match.group(1).split())
    right = " ".join(match.group(2).split())
    if not left or not right:
        return None
    return f"{left} vs {right}"


def parse_box_live_schedule(
    html: str,
    today: date,
    source_url: str = BOX_LIVE_FEED_URL,
) -> list[DiscoveredEvent]:
    soup = BeautifulSoup(html, "html.parser")
    found: dict[tuple[str, date], DiscoveredEvent] = {}

    # Each top-level card is a .card_holders element. Undercards are nested in
    # .undercard_contest elements and must not become separate calendar cards.
    for card in soup.select(".card_holders"):
        heading = card.find("h3")
        date_heading = card.find_previous("h2")
        if heading is None or date_heading is None:
            continue
        event_date = _event_date(date_heading.get_text(" ", strip=True))
        title = _title(heading.get_text(" ", strip=True))
        if event_date is None or event_date < today or title is None:
            continue
        found[(title.casefold(), event_date)] = DiscoveredEvent(
            title,
            event_date,
            source_url,
        )

    return sorted(found.values(), key=lambda event: (event.event_date, event.title))


def fetch_box_live_events(today: date | None = None) -> list[DiscoveredEvent]:
    today = today or date.today()
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "Chrome/126.0 Safari/537.36 MajorBoxingCalendar/1.0"
        ),
        "Accept-Language": "en-AU,en;q=0.9",
    }
    try:
        response = requests.get(BOX_LIVE_FEED_URL, timeout=30, headers=headers)
    except requests.RequestException as exc:
        raise BoxLiveSourceError(f"Unable to fetch Box.Live: {exc}") from exc
    if response.status_code != 200:
        raise BoxLiveSourceError(f"Box.Live returned HTTP {response.status_code}")

    events = parse_box_live_schedule(response.text, today)
    if len(events) < BOX_LIVE_MIN_EVENTS:
        raise BoxLiveSourceError(
            "Safety stop: expected at least "
            f"{BOX_LIVE_MIN_EVENTS} Box.Live schedule entries, parsed {len(events)}"
        )
    return events

"""Supplementary discovery from The Ring's public aggregate schedule."""
from __future__ import annotations

import re
from datetime import date

import requests
from dateutil import parser as date_parser

from scripts.models import DiscoveredEvent
from scripts.sources.common import OfficialSourceError, _clean_fighter, looks_like_fight
from scripts.sources import http


RING_SCHEDULE_API = "https://www.ringmagazine.com/api/cached/v1/content/search/events/upcoming"

# The aggregate may cover smaller divisions outside this calendar's scope.
EXCLUDED_DIVISIONS = {
    "flyweight", "juniorflyweight", "lightflyweight", "miniflyweight",
    "minimumweight", "minimumflyweight", "strawweight", "juniorstrawweight",
    "lightminimumweight", "atomweight", "superatomweight", "pinweight",
}


def is_flyweight_or_lighter(weight_class: object) -> bool:
    if not isinstance(weight_class, str):
        return False  # Unknown divisions remain review leads rather than guesses.
    label = re.split(r"[\d(]", weight_class, maxsplit=1)[0].casefold()
    division = re.sub(r"[^a-z]", "", label)
    return division in EXCLUDED_DIVISIONS


def parse_ring_schedule(payload: object, today: date) -> list[DiscoveredEvent]:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise OfficialSourceError("The Ring returned an invalid schedule response")
    pagination = payload.get("pagination")
    rows = payload["data"]
    if (not isinstance(pagination, dict)
            or pagination.get("hasNextPage") is not False
            or not isinstance(pagination.get("total"), int)
            or pagination["total"] != len(rows)):
        raise OfficialSourceError("Safety stop: The Ring schedule is incomplete")
    events: dict[str, DiscoveredEvent] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise OfficialSourceError("The Ring returned an invalid event")
        event_id = row.get("id")
        fights = row.get("fights")
        if not isinstance(event_id, str) or not re.fullmatch(r"[A-Za-z0-9]+", event_id):
            raise OfficialSourceError("The Ring returned an invalid event ID")
        if not isinstance(fights, list):
            raise OfficialSourceError("The Ring returned invalid bout data")
        headlines = [f for f in fights if isinstance(f, dict) and f.get("isMainEvent") is True]
        # Never infer the headline from the first undercard bout.
        if len(headlines) != 1:
            raise OfficialSourceError("Safety stop: The Ring event has no unique main event")
        fight = headlines[0]
        if is_flyweight_or_lighter(fight.get("weightClass")):
            continue
        names = []
        for side in ("fighterA", "fighterB"):
            fighter = fight.get(side)
            name = fighter.get("name") if isinstance(fighter, dict) else None
            if not isinstance(name, str) or not name.strip():
                raise OfficialSourceError("The Ring main event has missing fighter names")
            names.append(_clean_fighter(name))
        if not looks_like_fight(*names):
            raise OfficialSourceError("The Ring main event has invalid fighter names")
        try:
            start = date_parser.isoparse(row["eventStart"])
            if start.tzinfo is None:
                raise ValueError("missing timezone")
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise OfficialSourceError("The Ring returned an invalid event date") from exc
        # This date is a discovery reference only, never an approved broadcast time.
        event_date = start.date()
        if event_date < today:
            continue
        event = DiscoveredEvent(
            f"{names[0]} vs {names[1]}", event_date,
            f"https://www.ringmagazine.com/events/{event_id}", card_role="main_event",
        )
        if event_id in events and events[event_id] != event:
            raise OfficialSourceError("The Ring returned conflicting duplicate events")
        events[event_id] = event
    return sorted(events.values(), key=lambda event: (event.event_date, event.title))


def fetch_ring_events(today: date, headers: dict[str, str]) -> list[DiscoveredEvent]:
    try:
        response = http.get(
            RING_SCHEDULE_API, params={"limit": 100, "language": "en", "_ttl": 60},
            timeout=30, headers=headers,
        )
        if response.status_code != 200:
            raise OfficialSourceError(f"The Ring returned HTTP {response.status_code}")
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise OfficialSourceError(f"Unable to fetch The Ring schedule: {exc}") from exc
    events = parse_ring_schedule(payload, today)
    if not events:
        raise OfficialSourceError("Safety stop: The Ring parsed 0 upcoming schedule entries")
    return events

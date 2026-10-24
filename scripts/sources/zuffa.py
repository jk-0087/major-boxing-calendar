"""ZUFFA schedule-specific parsing."""
from __future__ import annotations

import re
from datetime import date
from bs4 import BeautifulSoup
from scripts.models import DiscoveredEvent
from scripts.sources.common import (
    SourceSpec, FIGHT_RE, _clean, _clean_fighter, _parse_date, looks_like_fight,
)


def parse_zuffa_headlines(
    soup: BeautifulSoup,
    spec: SourceSpec,
    today: date,
) -> list[DiscoveredEvent]:
    """Read official headline features even when their links only sell tickets."""
    found: dict[tuple[str, date], DiscoveredEvent] = {}
    for block in soup.select(".fifty-fifty__text-block"):
        heading = block.select_one(".fifty-fifty__title")
        body = block.select_one(".fifty-fifty__body")
        if heading is None or body is None:
            continue
        text = _clean(body.get_text(" ", strip=True))
        if not re.search(r"\b(?:main[ -]event|headline\w*)\b", text, re.I):
            continue
        fight = FIGHT_RE.fullmatch(_clean(heading.get_text(" ", strip=True)))
        event_date = _parse_date(text, today)
        if fight is None or event_date is None or event_date < today:
            continue
        left, right = (_clean_fighter(fight.group(side)) for side in ("a", "b"))
        if not looks_like_fight(left, right):
            continue
        title = f"{left} vs {right}"
        # Keep the verifiable official source, not an external ticket shortlink.
        found[(title.casefold(), event_date)] = DiscoveredEvent(
            title, event_date, spec.url, card_role="main_event"
        )
    return sorted(found.values(), key=lambda event: (event.event_date, event.title))

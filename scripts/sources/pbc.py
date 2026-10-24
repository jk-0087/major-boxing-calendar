"""PBC schedule-specific parsing."""
from __future__ import annotations

import re
from datetime import date
from urllib.parse import urljoin, urlsplit
from bs4 import BeautifulSoup
from scripts.models import DiscoveredEvent
from scripts.sources.common import (
    SourceSpec, _clean_fighter, _parse_date, looks_like_fight,
)


def parse_pbc_schedule(
    soup: BeautifulSoup,
    spec: SourceSpec,
    today: date,
) -> list[DiscoveredEvent]:
    """Read redesigned PBC cards, whose first bout is the headline."""
    found: dict[tuple[str, date], DiscoveredEvent] = {}
    for card in soup.select(".pbc-schedule__fight-inner"):
        date_node = card.select_one(".pbc-schedule__date")
        bouts = card.select_one(".pbc-schedule__card")
        if date_node is None or bouts is None:
            continue
        event_date = _parse_date(date_node.get_text(" ", strip=True), today)
        if event_date is None or event_date < today:
            continue
        event_link = next(
            (anchor for anchor in bouts.select("a[href]")
             if re.fullmatch(r"/events/\d+/?", urlsplit(urljoin(spec.url, anchor["href"])).path)
             and source_is_pbc(urljoin(spec.url, anchor["href"]))),
            None,
        )
        headline = bouts.select_one("h2")
        if event_link is None or headline is None:
            continue
        # Two fighter spans avoid parsing hidden accessibility labels in 'vs'.
        names = headline.select("a > span")
        if len(names) != 2:
            continue
        left, right = (_clean_fighter(node.get_text(" ", strip=True)) for node in names)
        if not looks_like_fight(left, right):
            continue
        url = urljoin(spec.url, event_link["href"])
        found[(url, event_date)] = DiscoveredEvent(
            f"{left} vs {right}", event_date, url, card_role="main_event"
        )
    return sorted(found.values(), key=lambda event: (event.event_date, event.title))


def source_is_pbc(url: str) -> bool:
    return urlsplit(url).netloc.casefold() in {
        "premierboxingchampions.com", "www.premierboxingchampions.com"
    }

"""BOXXER schedule-specific parsing."""
from __future__ import annotations

from datetime import date
from urllib.parse import unquote, urljoin, urlsplit
from bs4 import BeautifulSoup
from scripts.models import DiscoveredEvent
from scripts.sources.common import (
    SourceSpec, FIGHT_RE, _clean, _clean_fighter, _parse_date, looks_like_fight,
)


def parse_boxxer_schedule(
    soup: BeautifulSoup,
    spec: SourceSpec,
    today: date,
) -> list[DiscoveredEvent]:
    """Pair BOXXER's linked fight headings with their own event dates."""
    found: dict[tuple[str, date], DiscoveredEvent] = {}
    for heading in soup.select("h2, h3, h4"):
        anchor = heading.select_one("a[href]")
        if anchor is None:
            continue
        url = urljoin(spec.url, anchor["href"])
        parsed_url = urlsplit(url)
        if parsed_url.netloc.casefold() not in {"www.boxxer.com", "boxxer.com"}:
            continue
        if not parsed_url.path.startswith("/events/"):
            continue
        fight = FIGHT_RE.fullmatch(_clean(anchor.get_text(" ", strip=True)))
        if fight is None:
            continue
        left, right = (_clean_fighter(fight.group(side)) for side in ("a", "b"))
        if not looks_like_fight(left, right):
            continue
        # Dated event slugs include a year, unlike the abbreviated card labels.
        event_date = _parse_date(unquote(parsed_url.path).replace("-", " "), today)
        if event_date is None:
            card = heading.find_parent(class_="elementor-widget-wrap")
            if card is not None:
                # Never borrow a date from a container holding multiple cards.
                linked_fights = [node for node in card.select("h2, h3, h4")
                                 if FIGHT_RE.fullmatch(_clean(node.get_text(" ", strip=True)))]
                if len(linked_fights) == 1:
                    event_date = _parse_date(card.get_text(" ", strip=True), today)
        if event_date is None or event_date < today:
            continue
        found[(url, event_date)] = DiscoveredEvent(
            f"{left} vs {right}", event_date, url, card_role="main_event"
        )
    return sorted(found.values(), key=lambda event: (event.event_date, event.title))

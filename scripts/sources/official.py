from __future__ import annotations

import re
import json
from dataclasses import dataclass
from datetime import date
from urllib.parse import unquote, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from scripts.models import DiscoveredEvent


@dataclass(frozen=True)
class SourceSpec:
    name: str
    url: str


OFFICIAL_SOURCES = (
    SourceSpec("Queensberry", "https://queensberry.co.uk/pages/events"),
    SourceSpec("Top Rank", "https://toprank.com/events/upcoming"),
    SourceSpec("The Ring / Riyadh Season", "https://www.ringmagazine.com/events"),
    SourceSpec("Premier Boxing Champions", "https://www.premierboxingchampions.com/boxing-schedule"),
    SourceSpec("Golden Boy", "https://www.goldenboy.com/events/"),
    SourceSpec("BOXXER", "https://www.boxxer.com/tickets/"),
    SourceSpec("No Limit Boxing", "https://nolimitboxing.com.au/events"),
    SourceSpec("Zuffa Boxing", "https://www.ufc.com/zuffaboxing"),
)

EDITORIAL_WORDS = {
    "angle",
    "anniversary",
    "delivered",
    "highlights",
    "hoodie",
    "interview",
    "post-show",
    "provides",
    "results",
    "scorecards",
    "shirt",
    "statement",
    "update",
    "video",
    "weigh-in",
}

MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|November|December|"
    "Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
)
DATE_RE = re.compile(
    rf"\b(?:(?:{MONTHS})\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,)?(?:\s+\d{{4}})?|"
    rf"\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{MONTHS})(?:\s+\d{{4}})?)\b",
    re.I,
)
NUMERIC_DATE_RE = re.compile(
    r"\b(?P<day>\d{1,2})\s*\|\s*(?P<month>\d{1,2})\s*\|\s*(?P<year>\d{2}|\d{4})\b"
)
FIGHT_RE = re.compile(
    r"(?P<a>[A-ZÀ-ÖØ-öø-ÿ][\wÀ-ÖØ-öø-ÿ.'’\- ]{1,55}?)\s*"
    r"(?:v(?:s\.?|\.)|versus)(?:\s*\(versus\))?\s*"
    r"(?P<b>[A-ZÀ-ÖØ-öø-ÿ][\wÀ-ÖØ-öø-ÿ.'’\- ]{1,55})",
    re.I,
)


class OfficialSourceError(RuntimeError):
    pass


def _clean(value: str) -> str:
    return " ".join(value.strip(" -–—:;,.\t\n").split())


def _clean_fighter(value: str) -> str:
    value = re.sub(r"\s+Tickets$", "", value, flags=re.I)
    value = re.sub(r"\s+Live on\s+.+$", "", value, flags=re.I)
    value = " ".join(part.strip("-–—") for part in _clean(value).split())
    if value.isupper() or value.islower():
        value = value.title()
    return value


def looks_like_fight(left: str, right: str) -> bool:
    words = {word.casefold().strip(".'’") for word in f"{left} {right}".split()}
    return (
        bool(left and right)
        and len(left.split()) <= 7
        and len(right.split()) <= 7
        and not words.intersection(EDITORIAL_WORDS)
    )


def _event_url_score(event: DiscoveredEvent) -> tuple[int, int]:
    slug = unquote(urlsplit(event.source_url).path).casefold()
    left, right = event.fighters
    surnames = [
        re.sub(r"[^a-z0-9]", "", fighter.casefold().rsplit(" ", 1)[-1])
        for fighter in (left, right)
    ]
    slug_compact = re.sub(r"[^a-z0-9]", "", slug)
    surname_matches = sum(bool(name and name in slug_compact) for name in surnames)
    return (1 if "fight-night" in slug else 0, surname_matches)


def select_main_events(
    events: list[DiscoveredEvent],
    spec: SourceSpec,
) -> list[DiscoveredEvent]:
    """Keep one headline for each event page, preferring URL-backed names."""
    grouped_cards: dict[tuple[str, date], list[DiscoveredEvent]] = {}
    listing_url = spec.url.rstrip("/")
    for event in events:
        # Structured schedule entries that only reference the listing URL can
        # represent distinct cards, so retain their title in the grouping key.
        source_key = event.source_url.rstrip("/")
        if source_key == listing_url:
            source_key = f"{source_key}#{event.title.casefold()}"
        key = (source_key, event.event_date)
        grouped_cards.setdefault(key, []).append(event)

    selected = []
    for candidates in grouped_cards.values():
        if len(candidates) == 1:
            selected.append(candidates[0])
            continue
        best_score = max(_event_url_score(event) for event in candidates)
        best = [
            event for event in candidates if _event_url_score(event) == best_score
        ]
        # Ambiguous multi-bout pages are safer to skip than to stage an
        # arbitrary undercard. A unique URL-backed fighter match is required.
        if len(best) == 1 and best_score > (0, 0):
            selected.append(best[0])

    if spec.name == "Premier Boxing Champions":
        # PBC exposes separate pages for every undercard bout alongside one
        # fight-night page. Prefer that card-level page for each advertised date.
        by_date: dict[date, list[DiscoveredEvent]] = {}
        for event in selected:
            by_date.setdefault(event.event_date, []).append(event)
        selected = []
        for candidates in by_date.values():
            if len(candidates) == 1:
                selected.append(candidates[0])
                continue
            fight_nights = [
                event
                for event in candidates
                if "fight-night" in urlsplit(event.source_url).path.casefold()
            ]
            if len(fight_nights) == 1:
                selected.append(fight_nights[0])

    return sorted(selected, key=lambda event: (event.event_date, event.title))


def _parse_date(value: str, today: date) -> date | None:
    numeric = NUMERIC_DATE_RE.search(value)
    if numeric:
        year = int(numeric.group("year"))
        if year < 100:
            year += 2000
        try:
            return date(year, int(numeric.group("month")), int(numeric.group("day")))
        except ValueError:
            return None
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
    date_line = -100

    # Prefer schema.org event data when a schedule exposes it.
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            payload = json.loads(script.string or script.get_text())
        except (json.JSONDecodeError, TypeError):
            continue
        stack = payload if isinstance(payload, list) else [payload]
        while stack:
            item = stack.pop()
            if isinstance(item, list):
                stack.extend(item)
                continue
            if not isinstance(item, dict):
                continue
            stack.extend(value for value in item.values() if isinstance(value, (dict, list)))
            if item.get("@type") not in {"Event", "SportsEvent"} or not item.get("startDate"):
                continue
            try:
                event_date = date_parser.parse(str(item["startDate"])).date()
            except (ValueError, OverflowError):
                continue
            fight = FIGHT_RE.search(str(item.get("name", "")))
            if not fight or event_date < today:
                continue
            left, right = _clean_fighter(fight.group("a")), _clean_fighter(fight.group("b"))
            if looks_like_fight(left, right):
                title = f"{left} vs {right}"
                found[(title.casefold(), event_date)] = DiscoveredEvent(
                    title,
                    event_date,
                    spec.url,
                    card_role="main_event",
                )

    # Event-card links are more reliable than unrestricted page text on sites
    # that mix schedules with news, merchandise, and historical content.
    for anchor in soup.select("a[href]"):
        href = urljoin(spec.url, anchor.get("href", ""))
        anchor_text = _clean(anchor.get_text(" ", strip=True))
        if not (
            FIGHT_RE.search(anchor_text)
            or re.search(r"/(?:events?/|event-details/|the-event/|fight-night-)[^?#]+", href, re.I)
            or re.search(r"/pages/[^?#]*-vs-", href, re.I)
        ):
            continue
        candidates = [anchor_text]
        parent = anchor
        for _ in range(8):
            text = _clean(parent.get_text(" ", strip=True))
            event_date = _parse_date(text, today)
            if event_date and event_date >= today:
                candidates.extend(
                    _clean(node.get_text(" ", strip=True))
                    for node in parent.select("h1, h2, h3, h4, h5, h6")
                )
                strings = [_clean(value) for value in parent.stripped_strings]
                candidates.extend(strings)
                name_width = 2 if spec.name == "Queensberry" else 1
                candidates.extend(
                    f"{' '.join(strings[max(0, index - name_width):index])} vs "
                    f"{' '.join(strings[index + 1:index + 1 + name_width])}"
                    for index in range(1, len(strings) - 1)
                    if strings[index].casefold().rstrip(".") in {"v", "vs", "versus"}
                )
                for candidate in candidates:
                    fight = FIGHT_RE.fullmatch(candidate) or FIGHT_RE.search(candidate)
                    if not fight:
                        continue
                    left, right = _clean_fighter(fight.group("a")), _clean_fighter(fight.group("b"))
                    if looks_like_fight(left, right):
                        title = f"{left} vs {right}"
                        found[(title.casefold(), event_date)] = DiscoveredEvent(
                            title,
                            event_date,
                            href,
                            card_role="main_event",
                        )
                        break
                break
            parent = parent.parent
            if parent is None:
                break

    if spec in OFFICIAL_SOURCES:
        return select_main_events(list(found.values()), spec)

    for index, line in enumerate(lines):
        parsed = _parse_date(line, today)
        if parsed:
            current_date = parsed
            date_line = index
        if not current_date or current_date < today or index - date_line > 10:
            continue

        fight = FIGHT_RE.fullmatch(line) or FIGHT_RE.search(line)
        if fight:
            left = _clean_fighter(fight.group("a"))
            right = _clean_fighter(fight.group("b"))
        elif line.casefold().rstrip(".") in {"v", "vs", "versus"} and 0 < index < len(lines) - 1:
            left = _clean_fighter(lines[index - 1])
            right = _clean_fighter(lines[index + 1])
        else:
            continue

        if not looks_like_fight(left, right):
            continue
        if _parse_date(left, today) or _parse_date(right, today):
            continue
        title = f"{left} vs {right}"
        found[(title.casefold(), current_date)] = DiscoveredEvent(
            title,
            current_date,
            spec.url,
            card_role="main_event",
        )

    return sorted(found.values(), key=lambda event: (event.event_date, event.title))


def parse_no_limit_event_detail(
    html: str,
    source_url: str,
    today: date,
) -> DiscoveredEvent | None:
    soup = BeautifulSoup(html, "html.parser")
    page_text = _clean(soup.get_text(" ", strip=True))
    event_date = _parse_date(page_text, today)
    if not event_date or event_date < today:
        return None

    candidates = []
    if soup.title:
        candidates.append(_clean(soup.title.get_text(" ", strip=True).split("|", 1)[0]))
    candidates.extend(
        _clean(node.get_text(" ", strip=True))
        for node in soup.select("h1, h2, h3")
    )
    lines = [_clean(line) for line in soup.get_text("\n").splitlines() if _clean(line)]
    candidates.extend(lines)
    candidates.extend(
        f"{lines[index - 1]} vs {lines[index + 1]}"
        for index in range(1, len(lines) - 1)
        if lines[index].casefold().rstrip(".") in {"v", "vs", "versus"}
    )

    for candidate in candidates:
        fight = FIGHT_RE.fullmatch(candidate) or FIGHT_RE.search(candidate)
        if not fight:
            continue
        left = _clean_fighter(fight.group("a"))
        right = _clean_fighter(fight.group("b"))
        if looks_like_fight(left, right):
            return DiscoveredEvent(
                f"{left} vs {right}",
                event_date,
                source_url,
                card_role="main_event",
            )
    return None


def fetch_no_limit_events(
    listing_html: str,
    spec: SourceSpec,
    today: date,
    headers: dict[str, str],
) -> list[DiscoveredEvent]:
    soup = BeautifulSoup(listing_html, "html.parser")
    detail_urls = {
        urljoin(spec.url, anchor.get("href", ""))
        for anchor in soup.select('a[href*="/events/"]')
        if urljoin(spec.url, anchor.get("href", "")).rstrip("/")
        != spec.url.rstrip("/")
    }
    found: dict[tuple[str, date], DiscoveredEvent] = {}
    for detail_url in sorted(detail_urls):
        try:
            response = requests.get(detail_url, timeout=30, headers=headers)
        except requests.RequestException:
            continue
        if response.status_code != 200:
            continue
        event = parse_no_limit_event_detail(response.text, detail_url, today)
        if event:
            found[(event.title.casefold(), event.event_date)] = event
    return sorted(found.values(), key=lambda event: (event.event_date, event.title))


def fetch_official_events(spec: SourceSpec, today: date | None = None) -> list[DiscoveredEvent]:
    today = today or date.today()
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "Chrome/126.0 Safari/537.36 MajorBoxingCalendar/1.0"
        ),
        "Accept-Language": "en-AU,en;q=0.9",
    }
    try:
        response = requests.get(
            spec.url,
            timeout=30,
            headers=headers,
        )
    except requests.RequestException as exc:
        raise OfficialSourceError(f"Unable to fetch {spec.name}: {exc}") from exc
    if response.status_code != 200:
        raise OfficialSourceError(f"{spec.name} returned HTTP {response.status_code}")

    if spec.name == "No Limit Boxing":
        events = fetch_no_limit_events(response.text, spec, today, headers)
    else:
        events = parse_official_schedule(response.text, spec, today)
    if not events:
        raise OfficialSourceError(f"Safety stop: {spec.name} parsed 0 schedule entries")
    return events

"""Shared parsing primitives; no adapter imports or network calls."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from dateutil import parser as date_parser


@dataclass(frozen=True)
class SourceSpec:
    name: str
    url: str


EDITORIAL_WORDS = {
    "auction",
    "memorabilia",
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

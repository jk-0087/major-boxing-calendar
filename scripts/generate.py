#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]

def parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)

def utc_stamp(value: str) -> str:
    return parse_dt(value).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

def escape_ics(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace(",", "\\,")
        .replace(";", "\\;")
    )

SYDNEY = ZoneInfo("Australia/Sydney")


def friendly(
    value: str | None,
    confidence: str,
    timezone_name: str = "Australia/Sydney",
) -> str:
    if not value:
        return "TBA"
    rendered = (
        parse_dt(value)
        .astimezone(ZoneInfo(timezone_name))
        .strftime("%-I:%M %p %Z, %a %-d %b %Y")
    )
    return f"{rendered} ({confidence.title()})"

def current_time() -> datetime:
    override = os.environ.get("MBC_NOW")
    now = parse_dt(override) if override else datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("MBC_NOW must include a timezone offset")
    return now

def fold_ics_line(line: str) -> str:
    """Fold content lines to 75 UTF-8 octets, including continuation spaces."""
    parts: list[str] = []
    current = ""
    size = 0
    for character in line:
        width = len(character.encode("utf-8"))
        if size + width > 75:
            parts.append(current)
            current, size = " ", 1
        current += character
        size += width
    parts.append(current)
    return "\r\n".join(parts)


def render(events: list[dict], now: datetime | None = None) -> tuple[str, str]:
    """Render without changing data or writing files."""
    events = sorted(events, key=lambda item: parse_dt(item["main_card_start"]["value"]))
    now = now or current_time()
    if now.tzinfo is None:
        raise ValueError("Generation time must include a timezone offset")

    ics_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Major Boxing Calendar v4//jk-0087//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Major Boxing Calendar",
        "X-WR-TIMEZONE:Australia/Sydney",
        "X-WR-CALDESC:Curated major professional boxing events in Australian Eastern Time.",
        "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
        "X-PUBLISHED-TTL:PT12H",
    ]

    cards = []

    for event in events:
        checked_at = max((source["checked_at"] for source in event["sources"]), key=parse_dt)
        checked_dt = parse_dt(checked_at)
        source_url = event["sources"][0]["url"]
        venue_timezone = event["venue"]["timezone"]
        venue_local_start = (
            friendly(
                event["main_card_start"]["value"],
                event["main_card_start"]["confidence"],
                venue_timezone,
            )
            if venue_timezone
            else "TBA (venue timezone not yet confirmed)"
        )

        description = (
            f"Status\n{event['status']}\n\n"
            f"Promotion\n{', '.join(event['promotion'])}\n\n"
            f"City\n{event['venue']['city']}\n\n"
            f"Country\n{event['venue']['country']}\n\n"
            f"Titles\n" + "\n".join(event["titles"]) + "\n\n"
            f"Australia\n{event['broadcast']['australia']}\n\n"
            f"Main Card Start (Sydney)\n{friendly(event['main_card_start']['value'], event['main_card_start']['confidence'])}\n\n"
            f"Venue Local Start\n{venue_local_start}\n\n"
            f"Estimated Finish\n{friendly(event['end']['value'], event['end']['confidence'])}\n\n"
            f"Ring Walk\n{friendly(event['ring_walk']['value'], event['ring_walk']['confidence'])}\n\n"
            f"Main Card Bouts\n" + "\n".join(event["main_card"]) + "\n\n"
            f"Official / Schedule Source\n{source_url}\n\n"
            f"Verified\n{checked_dt.astimezone(SYDNEY).strftime('%d %b %Y, %-I:%M %p %Z')}"
        )

        modified = checked_dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        ics_lines.extend([
            "BEGIN:VEVENT",
            f"UID:{event['uid']}",
            f"DTSTAMP:{modified}",
            f"LAST-MODIFIED:{modified}",
            f"SEQUENCE:{event['sequence']}",
            f"DTSTART:{utc_stamp(event['main_card_start']['value'])}",
            f"DTEND:{utc_stamp(event['end']['value'])}",
            f"SUMMARY:{escape_ics(event['title'])}",
            f"LOCATION:{escape_ics(event['venue']['name'])}",
            f"DESCRIPTION:{escape_ics(description)}",
            f"URL:{source_url}",
            "STATUS:CANCELLED" if event["status"] == "Cancelled" else "STATUS:CONFIRMED",
            "TRANSP:TRANSPARENT",
            "END:VEVENT",
        ])

        # Keep completed cards in the source data and subscription feed, but remove
        # them from the public upcoming-events page after their estimated finish.
        if parse_dt(event["end"]["value"]) > now:
            date_label = (
                parse_dt(event["main_card_start"]["value"])
                .astimezone(SYDNEY)
                .strftime("%-d %b")
            )
            cards.append(
                '<article class="event">'
                f'<div class="date">{html.escape(date_label)}</div>'
                '<div>'
                f'<h2>{html.escape(event["title"])}</h2>'
                f'<p>{html.escape(event["venue"]["name"])} · {html.escape(event["venue"]["city"])}</p>'
                f'<p><strong>{html.escape(event["status"])}</strong> · '
                f'{html.escape(event["broadcast"]["australia"])}</p>'
                '</div>'
                '</article>'
            )

    ics_lines.append("END:VCALENDAR")
    calendar = "\r\n".join(fold_ics_line(line) for line in ics_lines) + "\r\n"

    index_html = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Major Boxing Calendar</title>
<style>
:root {
  color-scheme: dark;
  --background: #090b0f;
  --surface: #141820;
  --surface-hover: #191e28;
  --text: #f4f6fa;
  --muted: #a7b0bf;
  --border: #2a313d;
  --accent: #f2c14e;
  --accent-text: #171006;
}
* { box-sizing: border-box; }
html { min-height: 100%; background: var(--background); }
body {
  max-width: 860px;
  min-height: 100vh;
  margin: 0 auto;
  padding: 48px 24px 72px;
  color: var(--text);
  background:
    radial-gradient(circle at top right, rgba(242, 193, 78, 0.09), transparent 32rem),
    var(--background);
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  line-height: 1.5;
}
header { margin-bottom: 40px; }
h1 { margin: 0 0 8px; font-size: clamp(2rem, 6vw, 3.25rem); letter-spacing: -0.04em; }
h2 { margin: 0 0 6px; font-size: 1.2rem; line-height: 1.3; }
p { margin: 4px 0; color: var(--muted); }
.button {
  display: inline-block;
  margin-top: 20px;
  padding: 11px 16px;
  border: 1px solid var(--accent);
  border-radius: 9px;
  color: var(--accent-text);
  background: var(--accent);
  font-weight: 700;
  text-decoration: none;
  transition: transform 150ms ease, filter 150ms ease;
}
.button:hover { filter: brightness(1.08); transform: translateY(-1px); }
.button:focus-visible { outline: 3px solid rgba(242, 193, 78, 0.4); outline-offset: 3px; }
main { display: grid; gap: 12px; }
.event {
  display: grid;
  grid-template-columns: 76px 1fr;
  gap: 20px;
  padding: 20px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface);
  transition: background 150ms ease, border-color 150ms ease;
}
.event:hover { border-color: #3a4453; background: var(--surface-hover); }
.date { color: var(--accent); font-size: 1.05rem; font-weight: 800; letter-spacing: 0.02em; }
@media (max-width: 560px) {
  body { padding: 32px 16px 48px; }
  header { margin-bottom: 32px; }
  .event { grid-template-columns: 1fr; gap: 8px; padding: 18px; }
}
</style>
</head>
<body>
<header>
<h1>Major Boxing Calendar</h1>
<p>Curated major professional boxing events with Australian times and broadcast details.</p>
<a class="button" href="major-boxing-calendar.ics">Subscribe / Download</a>
</header>
<main>
""" + "\n".join(cards) + """
</main>
</body>
</html>
"""

    return calendar, index_html


def generate(
    events_path: Path = ROOT / "data/events.json",
    output_dir: Path = ROOT,
    now: datetime | None = None,
) -> None:
    events = json.loads(events_path.read_text(encoding="utf-8"))
    calendar, website = render(events, now)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "major-boxing-calendar.ics").write_bytes(calendar.encode("utf-8"))
    (output_dir / "index.html").write_text(website, encoding="utf-8")
    count = website.count('class="event"')
    print(f"Generated calendar for {len(events)} events and website for {count} upcoming events.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", type=Path, default=ROOT / "data/events.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT)
    parser.add_argument("--now", help="Timezone-aware reference time (defaults to MBC_NOW or now)")
    args = parser.parse_args(argv)
    generate(args.events, args.output_dir, parse_dt(args.now) if args.now else None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

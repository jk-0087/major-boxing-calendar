#!/usr/bin/env python3
from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
events = json.loads((ROOT / "data/events.json").read_text(encoding="utf-8"))

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

def friendly(value: str | None, confidence: str) -> str:
    if not value:
        return "TBA"
    rendered = parse_dt(value).strftime("%-I:%M %p, %a %-d %b %Y")
    return f"{rendered} ({confidence.title()})"

events.sort(key=lambda item: item["main_card_start"]["value"] or "9999")

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
    checked_at = max(source["checked_at"] for source in event["sources"])
    checked_dt = parse_dt(checked_at)
    source_url = event["sources"][0]["url"]

    description = (
        f"Status\n{event['status']}\n\n"
        f"Promotion\n{', '.join(event['promotion'])}\n\n"
        f"City\n{event['venue']['city']}\n\n"
        f"Country\n{event['venue']['country']}\n\n"
        f"Titles\n" + "\n".join(event["titles"]) + "\n\n"
        f"Australia\n{event['broadcast']['australia']}\n\n"
        f"Main Card Start\n{friendly(event['main_card_start']['value'], event['main_card_start']['confidence'])}\n\n"
        f"Estimated Finish\n{friendly(event['end']['value'], event['end']['confidence'])}\n\n"
        f"Ring Walk\n{friendly(event['ring_walk']['value'], event['ring_walk']['confidence'])}\n\n"
        f"Main Card Bouts\n" + "\n".join(event["main_card"]) + "\n\n"
        f"Official / Schedule Source\n{source_url}\n\n"
        f"Verified\n{checked_dt.strftime('%d %b %Y, %-I:%M %p')}"
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

    date_label = parse_dt(event["main_card_start"]["value"]).strftime("%-d %b")
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
(ROOT / "major-boxing-calendar.ics").write_text(
    "\r\n".join(ics_lines) + "\r\n",
    encoding="utf-8",
)

index_html = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Major Boxing Calendar</title>
<style>
body { font-family: system-ui,-apple-system,sans-serif; max-width: 820px; margin: 0 auto; padding: 32px 20px; line-height: 1.5; }
header { margin-bottom: 36px; }
h1 { margin-bottom: 8px; }
.event { display: grid; grid-template-columns: 72px 1fr; gap: 18px; padding: 20px 0; border-top: 1px solid #ddd; }
.date { font-weight: 700; font-size: 1.1rem; }
h2 { font-size: 1.2rem; margin: 0 0 6px; }
p { margin: 4px 0; color: #444; }
.button { display: inline-block; padding: 11px 16px; border: 1px solid #111; border-radius: 8px; text-decoration: none; color: #111; }
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

(ROOT / "index.html").write_text(index_html, encoding="utf-8")
print(f"Generated calendar and website for {len(events)} events.")

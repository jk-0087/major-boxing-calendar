import html
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]


def utc_stamp(value: str) -> str:
    return datetime.fromisoformat(value).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def test_validation_and_generation():
    subprocess.run([sys.executable, str(ROOT / "scripts/validate.py")], check=True)
    website_now = datetime.fromisoformat("2026-08-09T00:00:00+10:00")
    env = {**os.environ, "MBC_NOW": website_now.isoformat()}
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/generate.py")],
        check=True,
        env=env,
    )

    events = json.loads((ROOT / "data/events.json").read_text(encoding="utf-8"))
    calendar = (ROOT / "major-boxing-calendar.ics").read_text(encoding="utf-8")
    website = (ROOT / "index.html").read_text(encoding="utf-8")

    assert calendar.count("BEGIN:VEVENT") == len(events)
    assert "X-WR-CALNAME:Major Boxing Calendar" in calendar
    upcoming = [
        event
        for event in events
        if datetime.fromisoformat(event["end"]["value"]) > website_now
    ]
    assert website.count('class="event"') == len(upcoming)

    for event in events:
        assert "main_card_start" in event
        assert "start" not in event
        assert f"UID:{event['uid']}" in calendar
        assert f"DTSTART:{utc_stamp(event['main_card_start']['value'])}" in calendar
        assert "Main Card Start (Sydney)" in calendar
        assert "Venue Local Start" in calendar
        venue_timezone = event["venue"]["timezone"]
        if venue_timezone:
            venue_start = (
                datetime.fromisoformat(event["main_card_start"]["value"])
                .astimezone(ZoneInfo(venue_timezone))
                .strftime("%-I:%M %p %Z\\, %a %-d %b %Y")
            )
            assert venue_start in calendar
        else:
            assert event["venue"]["city"] == "TBA"
        if event["ring_walk"]["value"]:
            assert utc_stamp(event["ring_walk"]["value"]) != utc_stamp(event["main_card_start"]["value"])

        if event in upcoming:
            assert html.escape(event["title"]) in website
            sydney_date = (
                datetime.fromisoformat(event["main_card_start"]["value"])
                .astimezone(ZoneInfo("Australia/Sydney"))
                .strftime("%-d %b")
            )
            assert f'<div class="date">{sydney_date}</div>' in website
        else:
            assert html.escape(event["title"]) not in website

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def utc_stamp(value: str) -> str:
    return datetime.fromisoformat(value).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def test_validation_and_generation():
    subprocess.run([sys.executable, str(ROOT / "scripts/validate.py")], check=True)
    subprocess.run([sys.executable, str(ROOT / "scripts/generate.py")], check=True)

    events = json.loads((ROOT / "data/events.json").read_text(encoding="utf-8"))
    calendar = (ROOT / "major-boxing-calendar.ics").read_text(encoding="utf-8")
    website = (ROOT / "index.html").read_text(encoding="utf-8")

    assert calendar.count("BEGIN:VEVENT") == len(events)
    assert "X-WR-CALNAME:Major Boxing Calendar" in calendar
    assert website.count('class="event"') == len(events)

    for event in events:
        assert "main_card_start" in event
        assert "start" not in event
        assert f"UID:{event['uid']}" in calendar
        assert f"DTSTART:{utc_stamp(event['main_card_start']['value'])}" in calendar
        if event["ring_walk"]["value"]:
            assert utc_stamp(event["ring_walk"]["value"]) != utc_stamp(event["main_card_start"]["value"])

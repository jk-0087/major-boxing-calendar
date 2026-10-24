import html
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from scripts.generate import fold_ics_line, generate, render

ROOT = Path(__file__).resolve().parents[1]


def utc_stamp(value: str) -> str:
    return datetime.fromisoformat(value).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def test_generated_calendar_and_website_are_current(tmp_path):
    website_now = datetime.fromisoformat("2026-10-24T12:00:00+11:00")
    events = json.loads((ROOT / "data/events.json").read_text(encoding="utf-8"))
    generate(ROOT / "data/events.json", tmp_path, website_now)
    raw_calendar = (tmp_path / "major-boxing-calendar.ics").read_bytes()
    assert all(len(line) <= 75 for line in raw_calendar.split(b"\r\n"))
    calendar = raw_calendar.decode("utf-8").replace("\r\n ", "")
    website = (tmp_path / "index.html").read_text(encoding="utf-8")

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


def test_folding_preserves_multibyte_characters_and_escaped_text():
    original = "DESCRIPTION:" + "é 🥊 \\n\\,\\;" * 40
    folded = fold_ics_line(original)
    assert folded.replace("\r\n ", "") == original
    assert all(len(line.encode("utf-8")) <= 75 for line in folded.split("\r\n"))


def test_render_orders_instants_not_local_dates_without_mutating_input():
    event = json.loads((ROOT / "data/events.json").read_text())[0]
    late, early = deepcopy(event), deepcopy(event)
    late.update(uid="late", title="Late vs Fight")
    early.update(uid="early", title="Early vs Fight")
    late["main_card_start"]["value"] = "2099-10-24T19:00:00-05:00"
    early["main_card_start"]["value"] = "2099-10-25T05:00:00+11:00"
    for item in (early, late):
        item["end"]["value"] = "2099-10-26T00:00:00+00:00"
    events = [late, early]
    before = deepcopy(events)
    now = datetime.fromisoformat("2099-10-01T00:00:00+00:00")
    calendar, website = render(events, now)
    assert calendar.index("UID:early") < calendar.index("UID:late")
    assert website.index("Early vs Fight") < website.index("Late vs Fight")
    assert events == before
    assert render(events, now) == (calendar, website)

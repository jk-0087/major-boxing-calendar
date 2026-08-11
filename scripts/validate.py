#!/usr/bin/env python3
import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ROOT = Path(__file__).resolve().parents[1]
events = json.loads((ROOT / "data/events.json").read_text(encoding="utf-8"))
proposals = json.loads(
    (ROOT / "data/proposed-events.json").read_text(encoding="utf-8")
)
errors = []
uids = set()


def validate_staged_events(
    approved_events: list[dict],
    staged_events: list[dict],
) -> list[str]:
    staged_errors: list[str] = []
    approved_sources = {
        source["url"]
        for event in approved_events
        for source in event.get("sources", [])
    }
    approved_titles = {event["title"].casefold() for event in approved_events}
    card_keys: set[tuple[str, str]] = set()
    required_fields = {"title", "date", "source", "card_role", "score"}

    for index, proposal in enumerate(staged_events, start=1):
        prefix = f"Staged event {index}"
        missing = sorted(required_fields - proposal.keys())
        if missing:
            staged_errors.append(f"{prefix}: missing {', '.join(missing)}")
            continue

        if proposal["card_role"] != "main_event":
            staged_errors.append(f"{prefix}: only main events may be staged")
        if " vs " not in proposal["title"]:
            staged_errors.append(f"{prefix}: title must identify a main-event matchup")
        try:
            date.fromisoformat(proposal["date"])
        except (TypeError, ValueError):
            staged_errors.append(f"{prefix}: invalid event date")

        card_key = (proposal["source"], proposal["date"])
        if card_key in card_keys:
            staged_errors.append(
                f"{prefix}: multiple bouts from one card cannot be staged"
            )
        card_keys.add(card_key)

        if proposal["source"] in approved_sources:
            staged_errors.append(
                f"{prefix}: source belongs to an already approved card"
            )
        if proposal["title"].casefold() in approved_titles:
            staged_errors.append(f"{prefix}: event is already approved")

    return staged_errors

for index, event in enumerate(events, start=1):
    prefix = f"Event {index}"
    if event["uid"] in uids:
        errors.append(f"{prefix}: duplicate UID {event['uid']}")
    uids.add(event["uid"])

    expected_title = f"{event['fighters']['red']} vs {event['fighters']['blue']}"
    if event["title"] != expected_title:
        errors.append(f"{prefix}: title does not match fighter names")

    if "start" in event:
        errors.append(f"{prefix}: legacy start field is not allowed; use main_card_start")
    if "main_card_start" not in event:
        errors.append(f"{prefix}: missing main_card_start")
        continue

    venue_timezone = event["venue"].get("timezone")
    if venue_timezone:
        try:
            ZoneInfo(venue_timezone)
        except ZoneInfoNotFoundError:
            errors.append(f"{prefix}: invalid venue timezone {venue_timezone}")
    elif event["venue"]["city"] != "TBA":
        errors.append(f"{prefix}: known venue city requires a venue timezone")

    for field in ("main_card_start", "end", "ring_walk"):
        value = event[field]["value"]
        if value:
            try:
                datetime.fromisoformat(value)
            except ValueError:
                errors.append(f"{prefix}: invalid ISO datetime in {field}")

    main_card_start = event["main_card_start"]["value"]
    end = event["end"]["value"]
    ring_walk = event["ring_walk"]["value"]
    if main_card_start and end:
        start_dt = datetime.fromisoformat(main_card_start)
        end_dt = datetime.fromisoformat(end)
        if end_dt <= start_dt:
            errors.append(f"{prefix}: end must be after main-card start")
        if ring_walk:
            ring_walk_dt = datetime.fromisoformat(ring_walk)
            if ring_walk_dt < start_dt or ring_walk_dt >= end_dt:
                errors.append(f"{prefix}: ring walk must be between main-card start and end")

    versions = [item["version"] for item in event["history"]]
    if versions != sorted(set(versions)):
        errors.append(f"{prefix}: history versions must be unique and ordered")
    if event["sequence"] < max(versions):
        errors.append(f"{prefix}: sequence is below latest history version")

errors.extend(validate_staged_events(events, proposals))

if errors:
    raise SystemExit("\n".join(errors))

print(f"Validated {len(events)} events and {len(proposals)} staged main events.")

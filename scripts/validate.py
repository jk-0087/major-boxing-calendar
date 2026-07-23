#!/usr/bin/env python3
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
events = json.loads((ROOT / "data/events.json").read_text(encoding="utf-8"))
errors = []
uids = set()

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

if errors:
    raise SystemExit("\n".join(errors))

print(f"Validated {len(events)} events.")

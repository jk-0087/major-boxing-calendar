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

    for field in ("start", "end", "ring_walk"):
        value = event[field]["value"]
        if value:
            try:
                datetime.fromisoformat(value)
            except ValueError:
                errors.append(f"{prefix}: invalid ISO datetime in {field}")

    start = event["start"]["value"]
    end = event["end"]["value"]
    if start and end and datetime.fromisoformat(end) <= datetime.fromisoformat(start):
        errors.append(f"{prefix}: end must be after start")

    versions = [item["version"] for item in event["history"]]
    if versions != sorted(set(versions)):
        errors.append(f"{prefix}: history versions must be unique and ordered")
    if event["sequence"] < max(versions):
        errors.append(f"{prefix}: sequence is below latest history version")

if errors:
    raise SystemExit("\n".join(errors))

print(f"Validated {len(events)} events.")

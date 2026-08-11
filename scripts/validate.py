#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ROOT = Path(__file__).resolve().parents[1]


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


def validate_events(events: list[dict]) -> list[str]:
    errors: list[str] = []
    uids: set[str] = set()
    required_fields = {
        "uid",
        "sequence",
        "status",
        "title",
        "fighters",
        "main_card_start",
        "end",
        "ring_walk",
        "venue",
        "sources",
        "history",
    }

    for index, event in enumerate(events, start=1):
        prefix = f"Event {index}"
        missing = sorted(required_fields - event.keys())
        if missing:
            errors.append(f"{prefix}: missing {', '.join(missing)}")
            continue

        if event["uid"] in uids:
            errors.append(f"{prefix}: duplicate UID {event['uid']}")
        uids.add(event["uid"])

        expected_title = f"{event['fighters']['red']} vs {event['fighters']['blue']}"
        if event["title"] != expected_title:
            errors.append(f"{prefix}: title does not match fighter names")

        if "start" in event:
            errors.append(
                f"{prefix}: legacy start field is not allowed; use main_card_start"
            )

        venue_timezone = event["venue"].get("timezone")
        if venue_timezone:
            try:
                ZoneInfo(venue_timezone)
            except ZoneInfoNotFoundError:
                errors.append(f"{prefix}: invalid venue timezone {venue_timezone}")
        elif event["venue"].get("city") != "TBA":
            errors.append(f"{prefix}: known venue city requires a venue timezone")

        parsed_times: dict[str, datetime] = {}
        for field in ("main_card_start", "end", "ring_walk"):
            value = event[field].get("value")
            if not value:
                continue
            try:
                parsed = datetime.fromisoformat(value)
            except (TypeError, ValueError):
                errors.append(f"{prefix}: invalid ISO datetime in {field}")
                continue
            if parsed.tzinfo is None:
                errors.append(f"{prefix}: {field} must include a timezone offset")
                continue
            parsed_times[field] = parsed

        start_dt = parsed_times.get("main_card_start")
        end_dt = parsed_times.get("end")
        ring_walk_dt = parsed_times.get("ring_walk")
        if start_dt and end_dt:
            if end_dt <= start_dt:
                errors.append(f"{prefix}: end must be after main-card start")
            if ring_walk_dt and (ring_walk_dt < start_dt or ring_walk_dt >= end_dt):
                errors.append(
                    f"{prefix}: ring walk must be between main-card start and end"
                )

        versions = [item["version"] for item in event["history"]]
        if not versions:
            errors.append(f"{prefix}: history must not be empty")
        elif versions != sorted(set(versions)):
            errors.append(
                f"{prefix}: history versions must be unique and ordered"
            )
        elif event["sequence"] < max(versions):
            errors.append(f"{prefix}: sequence is below latest history version")

    return errors


def _without_sequence(event: dict) -> dict:
    comparable = deepcopy(event)
    comparable.pop("sequence", None)
    return comparable


def validate_revision(
    previous_events: list[dict],
    current_events: list[dict],
) -> list[str]:
    """Protect stable UIDs, prevent deletions, and enforce sequence changes."""
    errors: list[str] = []
    previous_by_uid = {event["uid"]: event for event in previous_events}
    current_by_uid = {event["uid"]: event for event in current_events}

    for uid, previous in previous_by_uid.items():
        current = current_by_uid.get(uid)
        if current is None:
            errors.append(
                f"Revision: existing event {previous['title']} removed or UID changed"
            )
            continue

        changed = _without_sequence(previous) != _without_sequence(current)
        if changed and current["sequence"] <= previous["sequence"]:
            errors.append(
                f"Revision: {current['title']} changed without incrementing SEQUENCE"
            )
        if not changed and current["sequence"] != previous["sequence"]:
            errors.append(
                f"Revision: {current['title']} incremented SEQUENCE without an event change"
            )

    return errors


def events_from_git(ref: str) -> list[dict]:
    result = subprocess.run(
        ["git", "show", f"{ref}:data/events.json"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--previous-ref",
        help="Compare events.json with this Git revision for UID and sequence safety",
    )
    args = parser.parse_args(argv)

    events = json.loads((ROOT / "data/events.json").read_text(encoding="utf-8"))
    proposals = json.loads(
        (ROOT / "data/proposed-events.json").read_text(encoding="utf-8")
    )
    errors = validate_events(events)
    errors.extend(validate_staged_events(events, proposals))
    if args.previous_ref:
        errors.extend(validate_revision(events_from_git(args.previous_ref), events))

    if errors:
        raise SystemExit("\n".join(errors))

    print(
        f"Validated {len(events)} events and {len(proposals)} staged main events."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

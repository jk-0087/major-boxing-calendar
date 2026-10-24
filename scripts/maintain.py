#!/usr/bin/env python3
"""Preview/apply verified approvals and updates; never fetch or infer fight times."""
from __future__ import annotations

import argparse
import json
import re
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from unicodedata import normalize

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.discover import pair_score
from scripts.generate import current_time, render
from scripts.validate import validate_events, validate_revision, validate_staged_events


def merge_patch(target: dict, patch: dict) -> None:
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            merge_patch(target[key], value)
        else:
            target[key] = deepcopy(value)


def prepare_change(
    events: list[dict], proposals: list[dict], action: str, selector: str,
    details: dict, note: str, now: datetime,
) -> tuple[list[dict], list[dict]]:
    if not isinstance(details, dict):
        raise ValueError("Details must be a JSON object")
    if {"uid", "sequence", "history"}.intersection(details):
        raise ValueError("UID, sequence and history are managed automatically")
    if not note.strip() or now.tzinfo is None:
        raise ValueError("A change note and timezone-aware reference time are required")
    errors = validate_events(events) or validate_staged_events(events, proposals)
    if errors:
        raise ValueError("\n".join(errors))
    updated, staged = deepcopy(events), deepcopy(proposals)
    stamp = now.replace(microsecond=0).isoformat()
    history = {"date": now.date().isoformat(), "changes": [note]}
    if action == "approve":
        matches = [p for p in staged if p["source"] == selector]
        if len(matches) != 1:
            raise ValueError("Select exactly one staged card by its source URL")
        proposal = matches[0]
        event = deepcopy(details)
        if pair_score(event.get("title", ""), proposal["title"]) < 0.90:
            raise ValueError("Details do not match the selected staged main event")
        title = normalize("NFKD", event["title"]).encode("ascii", "ignore").decode()
        slug = re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-")
        event["uid"] = f"mbc-{proposal['date']}-{slug}@jk-0087.github.io"
        event["sequence"] = 1
        event["history"] = [dict(history, version=1)]
        # Retain the exact staged provenance in addition to verified details.
        if "sources" in event and (not isinstance(event["sources"], list)
                                   or not all(isinstance(s, dict) for s in event["sources"])):
            raise ValueError("Sources must be a list of verified source objects")
        if not any(s.get("url") == selector for s in event.get("sources", [])):
            event.setdefault("sources", []).append({
                "url": selector, "publisher": "Approved schedule source", "checked_at": stamp,
            })
        updated.append(event)
        staged = [p for p in staged if p is not proposal]
    elif action == "update":
        matches = [e for e in updated if e["uid"] == selector]
        if len(matches) != 1:
            raise ValueError("Select exactly one approved event by its stable UID")
        event = matches[0]
        before = deepcopy(event)
        merge_patch(event, details)
        if event == before:
            return updated, staged
        event["sequence"] += 1
        event["history"].append(dict(history, version=event["sequence"]))
        if (isinstance(event.get("sources"), list) and event["sources"]
                and isinstance(event["sources"][0], dict)):
            event["sources"][0]["checked_at"] = stamp
    else:
        raise ValueError("Unknown maintenance action")
    errors = validate_events(updated)
    if not errors:
        errors += validate_staged_events(updated, staged)
        errors += validate_revision(events, updated)
    if errors:
        raise ValueError("\n".join(errors))
    return updated, staged


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("approve", "update"))
    parser.add_argument("selector", help="Staged source URL (approve) or existing UID (update)")
    parser.add_argument("--details", required=True, type=Path, help="Verified event fields as JSON; partial fields allowed for updates")
    parser.add_argument("--note", required=True, help="Human-readable reason for the change")
    parser.add_argument("--apply", action="store_true", help="Write validated data and regenerate outputs; default is preview only")
    parser.add_argument("--root", type=Path, default=ROOT, help="Project directory (also supports isolated test copies)")
    args = parser.parse_args(argv)
    events_path, proposals_path = args.root / "data/events.json", args.root / "data/proposed-events.json"
    events, proposals = (json.loads(p.read_text(encoding="utf-8")) for p in (events_path, proposals_path))
    now = current_time()
    try:
        updated, staged = prepare_change(events, proposals, args.action, args.selector,
                                        json.loads(args.details.read_text(encoding="utf-8")), args.note, now)
        # Render before any writes so validation/render failures leave data untouched.
        calendar, website = render(updated, now)
    except (ValueError, TypeError, KeyError) as exc:
        parser.error(str(exc))
    if (events, proposals) == (updated, staged):
        print("No changes; revision numbers preserved.")
        return 0
    if not args.apply:
        print(json.dumps({"events": updated, "staged": staged}, indent=2, ensure_ascii=False))
        print("Preview only. Add --apply to save and regenerate.")
        return 0
    for path, value in ((events_path, updated), (proposals_path, staged)):
        path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (args.root / "major-boxing-calendar.ics").write_bytes(calendar.encode("utf-8"))
    (args.root / "index.html").write_text(website, encoding="utf-8")
    print("Applied validated change and regenerated calendar and website. Review before committing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

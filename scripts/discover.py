#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from copy import deepcopy
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.models import DiscoveredEvent
from scripts.sources.dazn import DAZN_SCHEDULE_URL, DaznSourceError, fetch_dazn_events

EVENTS_PATH = ROOT / "data/events.json"
PROPOSALS_PATH = ROOT / "data/proposed-events.json"
SYDNEY = ZoneInfo("Australia/Sydney")

ALIASES = {
    "jr": "",
    "junior": "",
    "ii": "",
    "iii": "",
}

def normalise_name(value: str) -> str:
    value = value.casefold().replace("’", "'")
    value = re.sub(r"[^a-z0-9' ]+", " ", value)
    words = [ALIASES.get(word, word) for word in value.split()]
    return " ".join(word for word in words if word)

def fighter_pair(title: str) -> tuple[str, str]:
    if " vs " not in title:
        return normalise_name(title), ""
    left, right = title.split(" vs ", 1)
    return normalise_name(left), normalise_name(right)

def pair_score(existing_title: str, discovered_title: str) -> float:
    e1, e2 = fighter_pair(existing_title)
    d1, d2 = fighter_pair(discovered_title)
    direct = (SequenceMatcher(None, e1, d1).ratio() + SequenceMatcher(None, e2, d2).ratio()) / 2
    reverse = (SequenceMatcher(None, e1, d2).ratio() + SequenceMatcher(None, e2, d1).ratio()) / 2
    return max(direct, reverse)

def date_score(existing: dict, discovered: DiscoveredEvent) -> bool:
    start = existing.get("start", {}).get("value")
    if not start:
        return True
    existing_date = datetime.fromisoformat(start).astimezone(SYDNEY).date()
    return abs((existing_date - discovered.event_date).days) <= 14

def best_match(events: list[dict], discovered: DiscoveredEvent) -> tuple[dict | None, float]:
    candidates = [(event, pair_score(event["title"], discovered.title)) for event in events if date_score(event, discovered)]
    if not candidates:
        return None, 0.0
    return max(candidates, key=lambda item: item[1])

def update_existing(event: dict, discovered: DiscoveredEvent, checked_at: str) -> list[str]:
    changes: list[str] = []
    source = next((x for x in event["sources"] if "dazn.com" in x.get("url", "")), None)
    if source is None:
        event["sources"].append({"url": discovered.source_url, "publisher": "DAZN", "checked_at": checked_at})
        changes.append("Added DAZN schedule source")
    elif source.get("url") != discovered.source_url:
        source["url"] = discovered.source_url
        source["publisher"] = "DAZN"
        source["checked_at"] = checked_at
        changes.append("Updated DAZN schedule source")

    current_date = datetime.fromisoformat(event["start"]["value"]).astimezone(SYDNEY).date()
    if current_date != discovered.event_date:
        delta = discovered.event_date - current_date
        event["start"]["value"] = (datetime.fromisoformat(event["start"]["value"]) + timedelta(days=delta.days)).isoformat()
        event["end"]["value"] = (datetime.fromisoformat(event["end"]["value"]) + timedelta(days=delta.days)).isoformat()
        if event["ring_walk"].get("value"):
            event["ring_walk"]["value"] = (datetime.fromisoformat(event["ring_walk"]["value"]) + timedelta(days=delta.days)).isoformat()
        changes.append(f"Changed event date from {current_date.isoformat()} to {discovered.event_date.isoformat()}")

    if changes:
        event["sequence"] += 1
        next_version = max(item["version"] for item in event["history"]) + 1
        event["history"].append({
            "version": next_version,
            "date": checked_at[:10],
            "changes": changes,
        })
        for source_item in event["sources"]:
            if "dazn.com" in source_item.get("url", ""):
                source_item["checked_at"] = checked_at
    return changes

def run(apply: bool) -> int:
    existing = json.loads(EVENTS_PATH.read_text(encoding="utf-8"))
    try:
        discovered = fetch_dazn_events()
    except DaznSourceError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    checked_at = datetime.now(SYDNEY).replace(microsecond=0).isoformat()
    updated = deepcopy(existing)
    report = {"source": DAZN_SCHEDULE_URL, "checked_at": checked_at, "changes": [], "unmatched": []}

    matched_uids: set[str] = set()
    for item in discovered:
        match, score = best_match(updated, item)
        if match is not None and score >= 0.90 and match["uid"] not in matched_uids:
            matched_uids.add(match["uid"])
            changes = update_existing(match, item, checked_at)
            if changes:
                report["changes"].append({"uid": match["uid"], "title": match["title"], "score": round(score, 3), "changes": changes})
        elif item.event_date >= datetime.now(SYDNEY).date():
            report["unmatched"].append({"title": item.title, "date": item.event_date.isoformat(), "score": round(score, 3)})

    PROPOSALS_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if report["changes"] and apply:
        EVENTS_PATH.write_text(json.dumps(updated, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Applied {len(report['changes'])} matched event update(s).")
        return 10
    if report["changes"]:
        print(f"Dry run found {len(report['changes'])} matched event update(s).")
    else:
        print("No safe existing-event changes detected.")
    print(f"Staged {len(report['unmatched'])} unmatched future fight(s) for inspection.")
    return 0

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Write safe matched changes to events.json")
    args = parser.parse_args()
    raise SystemExit(run(args.apply))

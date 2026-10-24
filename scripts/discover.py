#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import date, datetime
from difflib import SequenceMatcher
from pathlib import Path
from time import perf_counter
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.models import DiscoveredEvent
from scripts.generate import current_time
from scripts.sources.matchroom import (
    MATCHROOM_EVENTS_URL,
    MatchroomSourceError,
    fetch_matchroom_events,
)
from scripts.sources.mvp import MVP_EVENTS_URL, MvpSourceError, fetch_mvp_events
from scripts.sources.official import (
    OFFICIAL_SOURCES,
    OfficialSourceError,
    fetch_official_events,
)

EVENTS_PATH = ROOT / "data/events.json"
PROPOSALS_PATH = ROOT / "data/proposed-events.json"
SYDNEY = ZoneInfo("Australia/Sydney")

ALIASES = {
    "jr": "",
    "junior": "",
    "ii": "",
    "iii": "",
    "2": "",
    "canelo": "alvarez",
    "o'leary": "leary",
}


def normalise_name(value: str) -> str:
    value = value.casefold().replace("’", "'")
    value = re.sub(r"[^a-z0-9' ]+", " ", value)
    words = [ALIASES.get(word, word) for word in value.split()]
    deduped = []
    for word in words:
        if word and (not deduped or deduped[-1] != word):
            deduped.append(word)
    return " ".join(deduped)


def fighter_pair(title: str) -> tuple[str, str]:
    if " vs " not in title:
        return normalise_name(title), ""
    left, right = title.split(" vs ", 1)
    return normalise_name(left), normalise_name(right)


def pair_score(existing_title: str, discovered_title: str) -> float:
    e1, e2 = fighter_pair(existing_title)
    d1, d2 = fighter_pair(discovered_title)
    e_surnames = (e1.rsplit(" ", 1)[-1] if e1 else "", e2.rsplit(" ", 1)[-1] if e2 else "")
    d_surnames = (d1.rsplit(" ", 1)[-1] if d1 else "", d2.rsplit(" ", 1)[-1] if d2 else "")
    if (
        e_surnames[0] == d_surnames[0]
        and e_surnames[1] == d_surnames[1]
    ) or (
        e_surnames[0] == d_surnames[1]
        and e_surnames[1] == d_surnames[0]
    ):
        return 1.0
    direct = (SequenceMatcher(None, e1, d1).ratio() + SequenceMatcher(None, e2, d2).ratio()) / 2
    reverse = (SequenceMatcher(None, e1, d2).ratio() + SequenceMatcher(None, e2, d1).ratio()) / 2
    return max(direct, reverse)


def date_score(existing: dict, discovered: DiscoveredEvent) -> bool:
    start = existing.get("main_card_start", {}).get("value")
    if not start:
        return True
    existing_date = datetime.fromisoformat(start).astimezone(SYDNEY).date()
    return abs((existing_date - discovered.event_date).days) <= 14


def best_match(events: list[dict], discovered: DiscoveredEvent) -> tuple[dict | None, float]:
    candidates = [(event, pair_score(event["title"], discovered.title)) for event in events if date_score(event, discovered)]
    if not candidates:
        return None, 0.0
    return max(candidates, key=lambda item: item[1])


def source_publisher(url: str) -> str:
    if "matchroomboxing.com" in url:
        return "Matchroom"
    if "mostvaluablepromotions.com" in url:
        return "Most Valuable Promotions"
    for spec in OFFICIAL_SOURCES:
        if spec.url.split("/")[2] in url:
            return spec.name
    return "Official source"


def source_domain(url: str) -> str:
    return urlsplit(url).netloc.casefold().removeprefix("www.")


def update_existing(event: dict, discovered: DiscoveredEvent, checked_at: str) -> list[str]:
    changes: list[str] = []
    publisher = source_publisher(discovered.source_url)
    domain = discovered.source_url.split("/")[2]
    source = next((x for x in event["sources"] if domain in x.get("url", "")), None)
    if source is None:
        event["sources"].append({"url": discovered.source_url, "publisher": publisher, "checked_at": checked_at})
        changes.append(f"Added {publisher} schedule source")
    else:
        if source.get("url") != discovered.source_url:
            source["url"] = discovered.source_url
            source["publisher"] = publisher
            source["checked_at"] = checked_at
            changes.append(f"Updated {publisher} schedule source")

    # Schedule adapters expose the advertised date at the venue, while stored
    # starts are Australian broadcast datetimes. Those dates commonly differ by
    # one day, so a date-only discovery must never rewrite a confirmed/estimated
    # Sydney start. Schedule changes require a timezone-aware verified update.

    if changes:
        event["sequence"] += 1
        next_version = max(item["version"] for item in event["history"]) + 1
        event["history"].append({"version": next_version, "date": checked_at[:10], "changes": changes})
    return changes


def is_supplementary(item: DiscoveredEvent) -> bool:
    return source_domain(item.source_url) == "ringmagazine.com"


def prefer_primary_sources(items: list[DiscoveredEvent]) -> list[DiscoveredEvent]:
    """Use Ring-only cards as leads; direct sources win overlapping discoveries."""
    primary = [item for item in items if not is_supplementary(item)]
    supplementary = [item for item in items if is_supplementary(item)]
    return primary + [item for item in supplementary if not any(
        abs((item.event_date - direct.event_date).days) <= 1
        and pair_score(item.title, direct.title) >= 0.90
        for direct in primary
    )]


def discover_all() -> tuple[list[DiscoveredEvent], list[dict]]:
    discovered: list[DiscoveredEvent] = []
    statuses: list[dict] = []
    today = current_time().astimezone(SYDNEY).date()

    # Sources are independent and network-bound, so fetch them concurrently.
    # Results are still processed in a fixed order to keep matching and output
    # deterministic. Only each adapter's expected source exception is skipped;
    # programming errors continue to fail the workflow.
    jobs = [
        (
            "Matchroom",
            MATCHROOM_EVENTS_URL,
            lambda: fetch_matchroom_events(today),
            MatchroomSourceError,
            "Primary Matchroom source skipped safely",
        ),
        (
            "Most Valuable Promotions",
            MVP_EVENTS_URL,
            lambda: fetch_mvp_events(today),
            MvpSourceError,
            "Optional MVP source skipped",
        ),
    ]
    jobs.extend(
        (
            spec.name,
            spec.url,
            lambda spec=spec: fetch_official_events(spec, today),
            OfficialSourceError,
            f"Optional {spec.name} source skipped",
        )
        for spec in OFFICIAL_SOURCES
    )

    def fetch_timed(job):
        name, url, fetch, error_type, error_label = job
        started = perf_counter()
        try:
            items = fetch()
            status = {"source": name, "url": url, "status": "ok", "events": len(items)}
        except error_type as exc:
            items = []
            status = {"source": name, "url": url, "status": "skipped", "error": str(exc)}
            print(f"{error_label}: {exc}", file=sys.stderr)
        status["duration_seconds"] = round(perf_counter() - started, 3)
        return items, status

    with ThreadPoolExecutor(max_workers=min(6, len(jobs))) as executor:
        futures = [executor.submit(fetch_timed, job) for job in jobs]
        for future in futures:
            items, status = future.result()
            discovered.extend(items)
            statuses.append(status)

    deduped: dict[tuple[str, object], DiscoveredEvent] = {}
    for item in prefer_primary_sources(discovered):
        deduped.setdefault((normalise_name(item.title), item.event_date), item)
    return sorted(deduped.values(), key=lambda x: (x.event_date, x.title)), statuses


def merge_staged_events(
    existing_proposals: list[dict],
    current_proposals: list[dict],
    statuses: list[dict],
    today: date,
) -> list[dict]:
    """Replace proposals only for healthy sources and preserve failed sources."""
    status_by_domain = {source_domain(item["url"]): item for item in statuses}
    previous_counts: dict[str, int] = {}
    for proposal in existing_proposals:
        domain = source_domain(proposal.get("source", ""))
        previous_counts[domain] = previous_counts.get(domain, 0) + 1

    healthy_domains = set()
    for domain, status in status_by_domain.items():
        if status["status"] != "ok":
            continue
        previous_count = previous_counts.get(domain, 0)
        current_count = int(status.get("events", 0))
        suspiciously_low = (
            previous_count >= 4
            and current_count < max(1, (previous_count + 1) // 2)
        )
        if suspiciously_low:
            status["proposal_policy"] = "preserved_previous_low_result"
            continue
        healthy_domains.add(domain)
    configured_domains = set(status_by_domain)

    candidates = []
    for proposal in existing_proposals:
        try:
            event_date = date.fromisoformat(proposal["date"])
            domain = source_domain(proposal["source"])
        except (KeyError, TypeError, ValueError):
            continue
        if event_date < today or domain not in configured_domains:
            continue
        if domain not in healthy_domains:
            candidates.append(proposal)

    candidates.extend(current_proposals)
    # A retained Ring lead can overlap a newly healthy direct source even when
    # the Ring fetch itself failed. Keep the direct proposal in that case.
    direct_proposals = [p for p in candidates
                        if source_domain(p["source"]) != "ringmagazine.com"]
    candidates = [p for p in candidates if source_domain(p["source"]) != "ringmagazine.com"
                  or not any(
                      abs((date.fromisoformat(p["date"]) - date.fromisoformat(d["date"])).days) <= 1
                      and pair_score(p["title"], d["title"]) >= 0.90
                      for d in direct_proposals
                  )]
    deduped: dict[tuple[str, str], dict] = {}
    for proposal in sorted(candidates, key=lambda item: (item["date"], item["title"])):
        key = (normalise_name(proposal["title"]), proposal["date"])
        deduped.setdefault(key, proposal)
    return list(deduped.values())


def update_source_health(statuses: list[dict], previous: dict, checked_at: str) -> dict:
    """Operational state is separate from approved events and their sequences."""
    state = {}
    for status in statuses:
        prior = previous.get(status["url"], {})
        if not isinstance(prior, dict):
            prior = {}
        failures = prior.get("consecutive_failures", 0)
        if type(failures) is not int or failures < 0:
            failures = 0
        healthy = status["status"] == "ok" and not status.get("proposal_policy")
        status["last_success_at"] = checked_at if healthy else prior.get("last_success_at")
        status["consecutive_failures"] = 0 if healthy else failures + 1
        state[status["url"]] = {
            "last_success_at": status["last_success_at"],
            "consecutive_failures": status["consecutive_failures"],
        }
    return state


def run(apply: bool, report_path: str | None = None, health_state_path: str | None = None) -> int:
    data_paths = {EVENTS_PATH.resolve(), PROPOSALS_PATH.resolve()}
    for output in (report_path, health_state_path):
        if output and Path(output).resolve() in data_paths:
            raise ValueError("Operational report paths must not overwrite approved or staged data")
    if report_path and health_state_path and Path(report_path).resolve() == Path(health_state_path).resolve():
        raise ValueError("Report and source-health history require distinct paths")
    existing = json.loads(EVENTS_PATH.read_text(encoding="utf-8"))
    existing_proposals = json.loads(PROPOSALS_PATH.read_text(encoding="utf-8"))
    discovered, statuses = discover_all()

    now = current_time().astimezone(SYDNEY)
    checked_at = now.replace(microsecond=0).isoformat()
    today = now.date()
    updated = deepcopy(existing)
    report = {
        "checked_at": checked_at,
        "sources": statuses,
        "changes": [],
        "current_unmatched": [],
        "staged": [],
    }

    matched_uids: set[str] = set()
    approved_card_sources = {
        source["url"]
        for event in updated
        for source in event.get("sources", [])
    }
    for item in prefer_primary_sources(discovered):
        if item.card_role != "main_event":
            continue
        match, score = best_match(updated, item)
        if match is not None and score >= 0.90:
            # The aggregate supplies review leads only. It cannot modify an
            # approved event, even when a direct source is temporarily down.
            if is_supplementary(item):
                continue
            if match["uid"] not in matched_uids:
                matched_uids.add(match["uid"])
                changes = update_existing(match, item, checked_at)
                if changes:
                    report["changes"].append({"uid": match["uid"], "title": match["title"], "score": round(score, 3), "changes": changes})
        elif (
            item.event_date >= today
            and item.source_url not in approved_card_sources
        ):
            report["current_unmatched"].append({
                "title": item.title,
                "date": item.event_date.isoformat(),
                "source": item.source_url,
                "card_role": item.card_role,
                "score": round(score, 3),
            })

    report["staged"] = merge_staged_events(
        existing_proposals,
        report["current_unmatched"],
        statuses,
        today,
    )
    previous_health = {}
    if health_state_path and Path(health_state_path).exists():
        try:
            previous_health = json.loads(Path(health_state_path).read_text(encoding="utf-8"))
            if not isinstance(previous_health, dict):
                raise ValueError("History must be an object")
        except (ValueError, OSError) as exc:
            print(f"Ignoring invalid operational history: {exc}", file=sys.stderr)
            previous_health = {}
    health = update_source_health(statuses, previous_health, checked_at)
    if apply:
        PROPOSALS_PATH.write_text(
            json.dumps(report["staged"], indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        if health_state_path:
            Path(health_state_path).write_text(json.dumps(health, indent=2) + "\n", encoding="utf-8")
    if report_path:
        Path(report_path).write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    if report["changes"] and apply:
        EVENTS_PATH.write_text(json.dumps(updated, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Applied {len(report['changes'])} matched event update(s).")
        return 10
    print("No safe existing-event changes detected." if not report["changes"] else f"Dry run found {len(report['changes'])} matched event update(s).")
    print(f"{'Staged' if apply else 'Would stage'} {len(report['staged'])} unmatched future fight(s) for inspection.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Write safe matched changes and the staged queue (otherwise read-only)")
    parser.add_argument("--report", help="Write a full source-health report to this path")
    parser.add_argument("--health-state", help="Optional operational history file; updated only with --apply")
    args = parser.parse_args()
    raise SystemExit(run(args.apply, args.report, args.health_state))

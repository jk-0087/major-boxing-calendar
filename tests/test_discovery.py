from datetime import date
from unittest.mock import patch
from scripts.discover import discover_all, pair_score, best_match, update_existing
from scripts.models import DiscoveredEvent
from scripts.sources.dazn import DaznSourceError
from scripts.sources.matchroom import MatchroomSourceError
from scripts.sources.official import OFFICIAL_SOURCES, OfficialSourceError


def sample_event():
    return {
        "uid": "stable-id@example.com",
        "sequence": 3,
        "title": "Errol Spence Jr vs Tim Tszyu",
        "start": {"value": "2026-07-26T11:00:00+10:00", "confidence": "estimated"},
        "end": {"value": "2026-07-26T16:00:00+10:00", "confidence": "estimated"},
        "ring_walk": {"value": "2026-07-26T14:30:00+10:00", "confidence": "estimated"},
        "sources": [],
        "history": [{"version": 3, "date": "2026-07-21", "changes": ["Migrated"]}],
    }


def test_name_matching_handles_junior_suffix():
    assert pair_score("Errol Spence Jr vs Tim Tszyu", "Errol Spence vs Tim Tszyu") > 0.95


def test_date_change_preserves_uid_and_increments_sequence():
    event = sample_event()
    discovered = DiscoveredEvent("Errol Spence vs Tim Tszyu", date(2026, 8, 2), "https://www.dazn.com/example")
    changes = update_existing(event, discovered, "2026-07-21T21:00:00+10:00")
    assert changes
    assert event["uid"] == "stable-id@example.com"
    assert event["sequence"] == 4
    assert event["start"]["value"].startswith("2026-08-02")


def test_matchroom_source_is_identified():
    event = sample_event()
    discovered = DiscoveredEvent(
        "Errol Spence vs Tim Tszyu",
        date(2026, 7, 26),
        "https://www.matchroomboxing.com/events/spence-vs-tszyu/",
    )
    changes = update_existing(event, discovered, "2026-07-21T21:00:00+10:00")
    assert "Added Matchroom schedule source" in changes
    assert event["sources"][0]["publisher"] == "Matchroom"


@patch(
    "scripts.discover.fetch_official_events",
    side_effect=OfficialSourceError("Official source unavailable"),
)
@patch("scripts.discover.fetch_dazn_events", side_effect=DaznSourceError("DAZN returned HTTP 403"))
@patch(
    "scripts.discover.fetch_matchroom_events",
    side_effect=MatchroomSourceError(
        "Safety stop: expected at least 2 Matchroom schedule entries, parsed 0"
    ),
)
def test_all_source_failures_are_safe_no_change(mock_matchroom, mock_dazn, mock_official):
    events, statuses = discover_all()
    assert events == []
    assert all(item["status"] == "skipped" for item in statuses)
    assert len(statuses) == 2 + len(OFFICIAL_SOURCES)
    assert "parsed 0" in statuses[0]["error"]
    assert "HTTP 403" in statuses[1]["error"]

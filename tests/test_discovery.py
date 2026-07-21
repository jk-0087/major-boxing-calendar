from datetime import date
from scripts.discover import pair_score, best_match, update_existing
from scripts.models import DiscoveredEvent


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

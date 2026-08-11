import json
from datetime import date
from unittest.mock import patch
from scripts.discover import discover_all, pair_score, best_match, run, update_existing
from scripts.models import DiscoveredEvent
from scripts.sources.matchroom import MatchroomSourceError
from scripts.sources.mvp import MvpSourceError
from scripts.sources.official import OFFICIAL_SOURCES, OfficialSourceError


def sample_event():
    return {
        "uid": "stable-id@example.com",
        "sequence": 3,
        "title": "Errol Spence Jr vs Tim Tszyu",
        "main_card_start": {"value": "2026-07-26T11:00:00+10:00", "confidence": "estimated"},
        "end": {"value": "2026-07-26T16:00:00+10:00", "confidence": "estimated"},
        "ring_walk": {"value": "2026-07-26T14:30:00+10:00", "confidence": "estimated"},
        "sources": [],
        "history": [{"version": 3, "date": "2026-07-21", "changes": ["Migrated"]}],
    }


def test_name_matching_handles_junior_suffix():
    assert pair_score("Errol Spence Jr vs Tim Tszyu", "Errol Spence vs Tim Tszyu") > 0.95


def test_name_matching_handles_surname_only_schedule_titles():
    assert pair_score(
        "Cherneka Johnson vs Dina Thorslund",
        "Johnson vs Thorslund",
    ) == 1.0
    assert pair_score(
        "Troy Williamson vs Callum Simpson",
        "Williamson vs Simpson 2",
    ) == 1.0


def test_name_matching_handles_schedule_aliases():
    assert pair_score(
        "Pierce O'Leary vs Mark Chamberlain",
        "Leary vs Chamberlain",
    ) == 1.0
    assert pair_score(
        "Canelo Alvarez vs Christian Mbilli",
        "Canelo vs Mbilli",
    ) == 1.0


def test_venue_date_does_not_rewrite_sydney_broadcast_date():
    event = sample_event()
    original_start = event["main_card_start"]["value"]
    original_end = event["end"]["value"]
    original_ring_walk = event["ring_walk"]["value"]
    discovered = DiscoveredEvent("Errol Spence vs Tim Tszyu", date(2026, 7, 25), "https://example.com/schedule")
    changes = update_existing(event, discovered, "2026-07-21T21:00:00+10:00")
    assert changes == ["Added Official source schedule source"]
    assert event["uid"] == "stable-id@example.com"
    assert event["sequence"] == 4
    assert event["main_card_start"]["value"] == original_start
    assert event["end"]["value"] == original_end
    assert event["ring_walk"]["value"] == original_ring_walk


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


@patch("scripts.discover.PROPOSALS_PATH")
@patch("scripts.discover.EVENTS_PATH")
@patch("scripts.discover.discover_all")
def test_duplicate_source_match_is_not_staged(
    mock_discover_all,
    mock_events_path,
    mock_proposals_path,
):
    event = sample_event()
    mock_events_path.read_text.return_value = json.dumps([event])
    mock_discover_all.return_value = (
        [
            DiscoveredEvent(
                "Errol Spence vs Tim Tszyu",
                date(2026, 7, 26),
                "https://example.com/first",
            ),
            DiscoveredEvent(
                "Spence vs Tszyu",
                date(2026, 7, 26),
                "https://example.org/second",
            ),
        ],
        [],
    )

    assert run(apply=False) == 0
    mock_proposals_path.write_text.assert_called_once_with(
        "[]\n",
        encoding="utf-8",
    )


@patch("scripts.discover.PROPOSALS_PATH")
@patch("scripts.discover.EVENTS_PATH")
@patch("scripts.discover.discover_all")
def test_undercard_discovery_is_not_staged(
    mock_discover_all,
    mock_events_path,
    mock_proposals_path,
):
    mock_events_path.read_text.return_value = "[]"
    mock_discover_all.return_value = (
        [
            DiscoveredEvent(
                "Undercard Fighter vs Another Fighter",
                date(2099, 8, 12),
                "https://example.com/card",
                card_role="undercard",
            )
        ],
        [],
    )

    assert run(apply=False) == 0
    mock_proposals_path.write_text.assert_called_once_with(
        "[]\n",
        encoding="utf-8",
    )


@patch("scripts.discover.PROPOSALS_PATH")
@patch("scripts.discover.EVENTS_PATH")
@patch("scripts.discover.discover_all")
def test_bout_from_approved_card_source_is_not_staged(
    mock_discover_all,
    mock_events_path,
    mock_proposals_path,
):
    event = sample_event()
    event["sources"] = [
        {
            "url": "https://example.com/approved-card",
            "publisher": "Official source",
            "checked_at": "2026-07-21T21:00:00+10:00",
        }
    ]
    mock_events_path.read_text.return_value = json.dumps([event])
    mock_discover_all.return_value = (
        [
            DiscoveredEvent(
                "Undercard Fighter vs Another Fighter",
                date(2099, 8, 12),
                "https://example.com/approved-card",
            )
        ],
        [],
    )

    assert run(apply=False) == 0
    mock_proposals_path.write_text.assert_called_once_with(
        "[]\n",
        encoding="utf-8",
    )


@patch("scripts.discover.fetch_mvp_events", side_effect=MvpSourceError("MVP unavailable"))
@patch(
    "scripts.discover.fetch_official_events",
    side_effect=OfficialSourceError("Official source unavailable"),
)
@patch(
    "scripts.discover.fetch_matchroom_events",
    side_effect=MatchroomSourceError(
        "Safety stop: expected at least 2 Matchroom schedule entries, parsed 0"
    ),
)
def test_all_source_failures_are_safe_no_change(
    mock_matchroom,
    mock_official,
    mock_mvp,
):
    events, statuses = discover_all()
    assert events == []
    assert all(item["status"] == "skipped" for item in statuses)
    assert len(statuses) == 2 + len(OFFICIAL_SOURCES)
    assert "parsed 0" in statuses[0]["error"]
    assert "MVP unavailable" in statuses[1]["error"]

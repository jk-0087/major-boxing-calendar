import json
from datetime import date
from unittest.mock import patch
from scripts.discover import (
    best_match,
    discover_all,
    merge_staged_events,
    pair_score,
    run,
    update_existing,
)
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
    discovered = DiscoveredEvent(
        "Errol Spence vs Tim Tszyu",
        date(2026, 7, 25),
        "https://example.com/schedule",
        card_role="main_event",
    )
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
        card_role="main_event",
    )
    changes = update_existing(event, discovered, "2026-07-21T21:00:00+10:00")
    assert "Added Matchroom schedule source" in changes
    assert event["sources"][0]["publisher"] == "Matchroom"


def test_unchanged_source_does_not_rewrite_event_verification_time():
    event = sample_event()
    event["sources"] = [
        {
            "url": "https://example.com/schedule",
            "publisher": "Official source",
            "checked_at": "2026-07-21T21:00:00+10:00",
        }
    ]
    discovered = DiscoveredEvent(
        event["title"],
        date(2026, 7, 26),
        "https://example.com/schedule",
        card_role="main_event",
    )
    assert update_existing(event, discovered, "2026-08-11T12:00:00+10:00") == []
    assert event["sources"][0]["checked_at"] == "2026-07-21T21:00:00+10:00"


def test_failed_source_proposals_are_preserved():
    proposal = {
        "title": "Future Fighter vs Future Challenger",
        "date": "2099-08-22",
        "source": "https://www.matchroomboxing.com/events/future-card/",
        "card_role": "main_event",
        "score": 0.2,
    }
    statuses = [
        {
            "source": "Matchroom",
            "url": "https://www.matchroomboxing.com/events/",
            "status": "skipped",
            "error": "timeout",
        }
    ]
    assert merge_staged_events([proposal], [], statuses, date(2026, 8, 11)) == [
        proposal
    ]


def test_healthy_source_replaces_its_previous_proposals():
    old = {
        "title": "Old Fighter vs Old Challenger",
        "date": "2099-08-22",
        "source": "https://www.matchroomboxing.com/events/old-card/",
        "card_role": "main_event",
        "score": 0.2,
    }
    new = {
        "title": "New Fighter vs New Challenger",
        "date": "2099-08-29",
        "source": "https://www.matchroomboxing.com/events/new-card/",
        "card_role": "main_event",
        "score": 0.3,
    }
    statuses = [
        {
            "source": "Matchroom",
            "url": "https://www.matchroomboxing.com/events/",
            "status": "ok",
            "events": 2,
        }
    ]
    assert merge_staged_events([old], [new], statuses, date(2026, 8, 11)) == [new]


def test_suspiciously_low_source_result_preserves_previous_proposals():
    previous = [
        {
            "title": f"Fighter {index} vs Challenger {index}",
            "date": f"2099-08-{20 + index:02d}",
            "source": f"https://example.com/card-{index}",
            "card_role": "main_event",
            "score": 0.2,
        }
        for index in range(4)
    ]
    current = [
        {
            "title": "Fighter 0 vs Challenger 0",
            "date": "2099-08-20",
            "source": "https://example.com/card-0",
            "card_role": "main_event",
            "score": 0.2,
        }
    ]
    statuses = [
        {
            "source": "Example",
            "url": "https://example.com/events",
            "status": "ok",
            "events": 1,
        }
    ]
    merged = merge_staged_events(previous, current, statuses, date(2026, 8, 11))
    assert merged == previous
    assert statuses[0]["proposal_policy"] == "preserved_previous_low_result"


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
    mock_proposals_path.read_text.return_value = "[]"
    mock_discover_all.return_value = (
        [
            DiscoveredEvent(
                "Errol Spence vs Tim Tszyu",
                date(2026, 7, 26),
                "https://example.com/first",
                card_role="main_event",
            ),
            DiscoveredEvent(
                "Spence vs Tszyu",
                date(2026, 7, 26),
                "https://example.org/second",
                card_role="main_event",
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
    mock_proposals_path.read_text.return_value = "[]"
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
    mock_proposals_path.read_text.return_value = "[]"
    mock_discover_all.return_value = (
        [
            DiscoveredEvent(
                "Undercard Fighter vs Another Fighter",
                date(2099, 8, 12),
                "https://example.com/approved-card",
                card_role="main_event",
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

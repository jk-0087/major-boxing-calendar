import json
import pytest
from datetime import date
from unittest.mock import patch
from scripts.discover import (
    best_match,
    discover_all,
    merge_staged_events,
    pair_score,
    prefer_primary_sources,
    run,
    update_existing,
    update_source_health,
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


def test_preview_changes_neither_approved_nor_staged_data(tmp_path):
    events_path, proposals_path = tmp_path / "events.json", tmp_path / "proposals.json"
    events_path.write_text(json.dumps([sample_event()]))
    proposals_path.write_text("[]\n")
    before = (events_path.read_bytes(), proposals_path.read_bytes())
    item = DiscoveredEvent("New Fighter vs Challenger", date(2099, 1, 1),
                           "https://example.com/new", "main_event")
    report_path = tmp_path / "report.json"
    health_path = tmp_path / "health.json"
    health_path.write_text("{}\n")
    with patch("scripts.discover.EVENTS_PATH", events_path), \
         patch("scripts.discover.PROPOSALS_PATH", proposals_path), \
         patch("scripts.discover.discover_all", return_value=([item], [])):
        assert run(False, str(report_path), str(health_path)) == 0
    assert (events_path.read_bytes(), proposals_path.read_bytes()) == before
    assert len(json.loads(report_path.read_text())["staged"]) == 1
    assert health_path.read_text() == "{}\n"


def test_reports_cannot_overwrite_calendar_data(tmp_path):
    data_path = tmp_path / "events.json"
    with patch("scripts.discover.EVENTS_PATH", data_path):
        with pytest.raises(ValueError, match="must not overwrite"):
            run(False, str(data_path))


def test_health_history_tracks_failures_and_recovers_separately():
    url = "https://example.com"
    ok = {"url": url, "status": "ok"}
    state = update_source_health([ok], {}, "first")
    assert ok["last_success_at"] == "first"
    for count in (1, 2):
        failed = {"url": url, "status": "skipped"}
        state = update_source_health([failed], state, "later")
        assert failed["consecutive_failures"] == count
        assert failed["last_success_at"] == "first"
    recovered = {"url": url, "status": "ok"}
    update_source_health([recovered], state, "recovered")
    assert recovered["consecutive_failures"] == 0
    assert recovered["last_success_at"] == "recovered"


def test_ring_yields_to_direct_source_and_preserves_ring_only_cards():
    ring = DiscoveredEvent("David Benavidez vs Michal Cieslak", date(2026, 12, 6),
                           "https://www.ringmagazine.com/events/Card123", "main_event")
    direct = DiscoveredEvent("Benavidez vs Cieslak", date(2026, 12, 5),
                             "https://www.premierboxingchampions.com/events/391735", "main_event")
    extra = DiscoveredEvent("ArAr Andales vs Raito Kataoka", date(2026, 10, 29),
                            "https://www.ringmagazine.com/events/Card456", "main_event")
    assert prefer_primary_sources([ring, extra, direct]) == [direct, extra]
    assert prefer_primary_sources([ring, extra]) == [ring, extra]


def test_ring_cannot_mutate_approved_events_but_stages_new_leads(tmp_path):
    events_path = tmp_path / "events.json"
    proposals_path = tmp_path / "proposals.json"
    event = sample_event()
    event["main_card_start"]["value"] = "2099-07-26T11:00:00+10:00"
    original = json.dumps([event])
    events_path.write_text(original)
    proposals_path.write_text("[]")
    items = [
        DiscoveredEvent("Spence vs Tszyu", date(2099, 7, 25),
                        "https://www.ringmagazine.com/events/Matched", "main_event"),
        DiscoveredEvent("ArAr Andales vs Raito Kataoka", date(2099, 10, 29),
                        "https://www.ringmagazine.com/events/NewCard", "main_event"),
    ]
    with patch("scripts.discover.EVENTS_PATH", events_path), \
         patch("scripts.discover.PROPOSALS_PATH", proposals_path), \
         patch("scripts.discover.discover_all", return_value=(items, [])):
        assert run(apply=True) == 0
    assert events_path.read_text() == original
    proposals = json.loads(proposals_path.read_text())
    assert [p["title"] for p in proposals] == ["ArAr Andales vs Raito Kataoka"]


def test_failed_ring_lead_yields_to_new_direct_proposal():
    ring = {"title": "David Benavidez vs Michal Cieslak", "date": "2026-12-06",
            "source": "https://www.ringmagazine.com/events/Card123", "card_role": "main_event", "score": 0.0}
    direct = {"title": "Benavidez vs Cieslak", "date": "2026-12-05",
              "source": "https://www.premierboxingchampions.com/events/391735", "card_role": "main_event", "score": 0.0}
    statuses = [
        {"url": "https://www.ringmagazine.com/events", "status": "skipped"},
        {"url": "https://www.premierboxingchampions.com/events/schedule", "status": "ok", "events": 1},
    ]
    assert merge_staged_events([ring], [direct], statuses, date(2026, 10, 24)) == [direct]


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

    assert run(apply=True) == 10
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

    assert run(apply=True) == 0
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

    assert run(apply=True) == 0
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

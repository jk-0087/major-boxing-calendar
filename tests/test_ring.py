from copy import deepcopy
from datetime import date
from unittest.mock import Mock, patch

import pytest

from scripts.sources.official import OFFICIAL_SOURCES, OfficialSourceError, fetch_official_events
from scripts.sources.ring import parse_ring_schedule


def schedule():
    return {
        "data": [{
            "id": "Card123",
            "eventStart": "2026-12-05T21:30:00.000Z",
            "fights": [
                {"isMainEvent": False, "fighterA": {"name": "Vergil Ortiz Jr."},
                 "fighterB": {"name": "Keith Thurman"}},
                {"isMainEvent": True, "startTime": "2026-12-06T04:00:00.000Z",
                 "fighterA": {"name": "David Benavidez"}, "fighterB": {"name": "Michal Cieslak"}},
            ],
        }],
        "pagination": {"total": 1, "hasNextPage": False, "limit": 100},
    }


def test_ring_uses_explicit_headline_event_date_and_stable_url():
    events = parse_ring_schedule(schedule(), date(2026, 10, 24))
    assert [(e.title, e.event_date, e.source_url, e.card_role) for e in events] == [
        ("David Benavidez vs Michal Cieslak", date(2026, 12, 5),
         "https://www.ringmagazine.com/events/Card123", "main_event")
    ]
    assert parse_ring_schedule(schedule(), date(2026, 12, 6)) == []


@pytest.mark.parametrize("division", ["Flyweight", "Junior flyweight", "Light-Flyweight",
    "Minimumweight", "Strawweight", "Atomweight", "Super atomweight", "Flyweight (112 lbs)"])
def test_ring_excludes_flyweight_and_lighter_headlines(division):
    payload = schedule()
    payload["data"][0]["fights"][1]["weightClass"] = division
    assert parse_ring_schedule(payload, date(2026, 10, 24)) == []


@pytest.mark.parametrize("division", ["Super flyweight", "Junior bantamweight", "Bantamweight",
    "Featherweight", "Cruiserweight", None, "Unknown"])
def test_ring_retains_higher_and_unknown_divisions_for_review(division):
    payload = schedule()
    payload["data"][0]["fights"][1]["weightClass"] = division
    # A small-division undercard never excludes a qualifying headline card.
    payload["data"][0]["fights"][0]["weightClass"] = "Flyweight"
    assert len(parse_ring_schedule(payload, date(2026, 10, 24))) == 1


@pytest.mark.parametrize("kind", ["more_pages", "missing_rows", "no_headline", "two_headlines",
                                  "bad_date", "bad_id", "missing_name", "missing_pagination"])
def test_ring_rejects_incomplete_or_ambiguous_data(kind):
    payload = schedule()
    row = payload["data"][0]
    if kind == "more_pages": payload["pagination"]["hasNextPage"] = True
    if kind == "missing_rows": payload["pagination"]["total"] = 2
    if kind == "no_headline": row["fights"][1]["isMainEvent"] = False
    if kind == "two_headlines": row["fights"][0]["isMainEvent"] = True
    if kind == "bad_date": row["eventStart"] = "unknown"
    if kind == "bad_id": row["id"] = "../../other"
    if kind == "missing_name": del row["fights"][1]["fighterB"]["name"]
    if kind == "missing_pagination": del payload["pagination"]
    with pytest.raises(OfficialSourceError):
        parse_ring_schedule(payload, date(2026, 10, 24))


def test_ring_reads_more_than_twenty_and_deduplicates_card_ids():
    payload = schedule()
    for i in range(25):
        row = deepcopy(payload["data"][0])
        row["id"] = f"Card{i}"
        payload["data"].append(row)
    payload["pagination"]["total"] = 26
    assert len(parse_ring_schedule(payload, date(2026, 10, 24))) == 26
    payload["data"].append(deepcopy(payload["data"][0]))
    payload["pagination"]["total"] = 27
    assert len(parse_ring_schedule(payload, date(2026, 10, 24))) == 26


@patch("scripts.sources.ring.requests.get")
def test_ring_fetch_uses_anonymous_schedule_and_preserves_safety(mock_get):
    spec = next(s for s in OFFICIAL_SOURCES if s.name == "The Ring / Riyadh Season")
    mock_get.return_value = Mock(status_code=200, json=Mock(return_value=schedule()))
    assert len(fetch_official_events(spec, date(2026, 10, 24))) == 1
    assert "/api/cached/v1/content/search/events/upcoming" in mock_get.call_args.args[0]
    assert mock_get.call_args.kwargs["params"]["limit"] == 100
    mock_get.return_value = Mock(status_code=403)
    with pytest.raises(OfficialSourceError, match="HTTP 403"):
        fetch_official_events(spec, date(2026, 10, 24))
    mock_get.return_value = Mock(status_code=200, json=Mock(return_value={
        "data": [], "pagination": {"total": 0, "hasNextPage": False}}))
    with pytest.raises(OfficialSourceError, match="parsed 0"):
        fetch_official_events(spec, date(2026, 10, 24))

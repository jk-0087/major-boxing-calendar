import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path

import pytest

from scripts.maintain import main, prepare_change

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime.fromisoformat("2026-10-24T12:00:00+11:00")


def sample():
    return json.loads((ROOT / "data/events.json").read_text())[0]


def test_update_preserves_identity_increments_once_and_records_history():
    event = sample()
    before = deepcopy(event)
    updated, staged = prepare_change([event], [], "update", event["uid"],
                                    {"venue": {"name": "Verified venue"}}, "Venue announced", NOW)
    result = updated[0]
    assert event == before
    assert result["uid"] == event["uid"]
    assert result["sequence"] == event["sequence"] + 1
    assert result["venue"]["city"] == event["venue"]["city"]
    assert result["history"][-1] == {"version": result["sequence"], "date": "2026-10-24", "changes": ["Venue announced"]}
    assert result["sources"][0]["checked_at"] == NOW.isoformat()
    assert staged == []
    again, _ = prepare_change(updated, [], "update", event["uid"],
                             {"venue": {"name": "Verified venue"}}, "Same venue", NOW)
    assert again == updated


@pytest.mark.parametrize("patch", [{"uid": "replacement"}, {"sequence": 99},
                                    {"history": []}, {"main_card_start": {"value": None}}])
def test_invalid_updates_leave_input_unchanged(patch):
    event = sample()
    before = deepcopy(event)
    with pytest.raises(ValueError):
        prepare_change([event], [], "update", event["uid"], patch, "Test", NOW)
    assert event == before


def approval_data():
    details = sample()
    for key in ("uid", "sequence", "history"):
        details.pop(key)
    proposal = {"title": details["title"], "date": "2026-07-25",
                "source": "https://example.com/new-card", "card_role": "main_event", "score": 0.0}
    return details, proposal


def test_approval_assigns_identity_and_removes_only_selected_proposal():
    details, proposal = approval_data()
    other = dict(proposal, title="Other Fighter vs Challenger", source="https://example.com/other")
    updated, staged = prepare_change([], [proposal, other], "approve", proposal["source"],
                                    details, "Approved verified card", NOW)
    assert updated[0]["sequence"] == 1
    assert updated[0]["uid"].startswith("mbc-2026-07-25-")
    assert updated[0]["sources"][-1]["url"] == proposal["source"]
    assert staged == [other]
    assert "uid" not in details


def test_approval_rejects_wrong_main_event():
    details, proposal = approval_data()
    details["title"] = "Wrong Fighter vs Wrong Challenger"
    with pytest.raises(ValueError, match="do not match"):
        prepare_change([], [proposal], "approve", proposal["source"], details, "Test", NOW)


def test_cli_preview_and_apply_in_isolated_project(tmp_path, monkeypatch, capsys):
    (tmp_path / "data").mkdir()
    event = sample()
    events_path = tmp_path / "data/events.json"
    proposals_path = tmp_path / "data/proposed-events.json"
    events_path.write_text(json.dumps([event]))
    proposals_path.write_text("[]")
    details_path = tmp_path / "verified.json"
    details_path.write_text(json.dumps({"venue": {"name": "Updated venue"}}))
    monkeypatch.setenv("MBC_NOW", NOW.isoformat())
    args = ["update", event["uid"], "--root", str(tmp_path), "--details", str(details_path), "--note", "Verified venue"]
    before = events_path.read_bytes()
    assert main(args) == 0
    capsys.readouterr()
    assert events_path.read_bytes() == before
    assert not (tmp_path / "index.html").exists()
    assert main(args + ["--apply"]) == 0
    assert json.loads(events_path.read_text())[0]["sequence"] == event["sequence"] + 1
    assert (tmp_path / "index.html").exists()
    assert (tmp_path / "major-boxing-calendar.ics").exists()

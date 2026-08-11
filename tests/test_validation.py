from scripts.validate import validate_staged_events


def approved_event():
    return {
        "title": "Main Fighter vs Challenger",
        "sources": [{"url": "https://example.com/approved-card"}],
    }


def staged_event(**overrides):
    proposal = {
        "title": "New Fighter vs New Challenger",
        "date": "2099-08-12",
        "source": "https://example.com/new-card",
        "card_role": "main_event",
        "score": 0.25,
    }
    proposal.update(overrides)
    return proposal


def test_staged_main_event_is_valid():
    assert validate_staged_events([approved_event()], [staged_event()]) == []


def test_staged_undercard_is_rejected():
    errors = validate_staged_events(
        [approved_event()],
        [staged_event(card_role="undercard")],
    )
    assert any("only main events" in error for error in errors)


def test_second_bout_from_same_card_is_rejected():
    errors = validate_staged_events(
        [],
        [
            staged_event(),
            staged_event(title="Another Fighter vs Other Challenger"),
        ],
    )
    assert any("multiple bouts from one card" in error for error in errors)


def test_bout_from_approved_card_source_is_rejected():
    errors = validate_staged_events(
        [approved_event()],
        [staged_event(source="https://example.com/approved-card")],
    )
    assert any("already approved card" in error for error in errors)

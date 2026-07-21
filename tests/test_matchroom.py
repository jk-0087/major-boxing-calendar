from datetime import date
from unittest.mock import Mock, patch

from scripts.sources.matchroom import fetch_matchroom_events

HTML = """
<html><body>
  <article>
    <span>Saturday 05 September 2026</span>
    <a href="/events/taylor-vs-pili/">Taylor VS Pili</a>
    <p>Venue Name, London, UK</p>
  </article>
  <article>
    <span>12 Aug 2026</span>
    <a href="/events/teremoana-vs-savage/">Teremoana VS Savage</a>
    <p>The Star, Gold Coast, Australia</p>
  </article>
</body></html>
"""


@patch("scripts.sources.matchroom.requests.get")
def test_matchroom_parser_extracts_event_cards(mock_get):
    response = Mock(status_code=200, text=HTML)
    mock_get.return_value = response
    events = fetch_matchroom_events(today=date(2026, 7, 21))
    assert [(event.title, event.event_date.isoformat()) for event in events] == [
        ("Teremoana vs Savage", "2026-08-12"),
        ("Taylor vs Pili", "2026-09-05"),
    ]
    assert events[0].source_url.endswith("/events/teremoana-vs-savage/")

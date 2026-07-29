from datetime import date
from unittest.mock import Mock, patch

import pytest

from scripts.sources.box_live import (
    BoxLiveSourceError,
    fetch_box_live_events,
    parse_box_live_schedule,
)


HTML = """
<html><body>
  <h2>Friday 4th September 2026</h2>
  <div class="card_holders">
    <h3>Ruiz Jr vs Knyba</h3>
    <div class="undercard_contest">
      <strong>Mielnicki Jr vs Williams</strong>
    </div>
  </div>
  <h2>Saturday 3rd October 2026</h2>
  <div class="card_holders">
    <h3>Whittaker vs Wallace</h3>
  </div>
</body></html>
"""


def test_box_live_parser_extracts_top_level_cards_only():
    events = parse_box_live_schedule(HTML, date(2026, 7, 29))
    assert [(event.title, event.event_date.isoformat()) for event in events] == [
        ("Ruiz Jr vs Knyba", "2026-09-04"),
        ("Whittaker vs Wallace", "2026-10-03"),
    ]


@patch("scripts.sources.box_live.requests.get")
def test_box_live_fetch_rejects_suspiciously_low_results(mock_get):
    mock_get.return_value = Mock(status_code=200, text=HTML)
    with pytest.raises(BoxLiveSourceError, match="expected at least"):
        fetch_box_live_events(today=date(2026, 7, 29))

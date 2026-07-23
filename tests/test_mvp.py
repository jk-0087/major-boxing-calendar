from datetime import date

from scripts.sources.mvp import parse_mvp_schedule


HTML = """
<html><body>
  <article><h3>MVPW 05 - Johnson vs Thorslund</h3><h2>SATURDAY - AUGUST 8, 2026</h2></article>
  <article><h3>Serrano vs Manzur</h3><h2>FRIDAY - AUGUST 21, 2026</h2></article>
  <article><h3>MVPW 06 - Mayer vs Cameron</h3><h2>SATURDAY - AUGUST 29, 2026</h2></article>
</body></html>
"""


def test_mvp_parser_handles_title_before_date_and_removes_series_prefix():
    events = parse_mvp_schedule(HTML, date(2026, 7, 23))
    assert [(event.title, event.event_date.isoformat()) for event in events] == [
        ("Johnson vs Thorslund", "2026-08-08"),
        ("Serrano vs Manzur", "2026-08-21"),
        ("Mayer vs Cameron", "2026-08-29"),
    ]

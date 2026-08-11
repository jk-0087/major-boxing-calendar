from datetime import date
from unittest.mock import Mock, patch

from scripts.models import DiscoveredEvent
from scripts.sources.official import (
    OFFICIAL_SOURCES,
    SourceSpec,
    fetch_official_events,
    parse_no_limit_event_detail,
    parse_official_schedule,
    select_main_events,
)


HTML = """
<html><body>
  <section>
    <span>Sat, Jul 25, 2026</span>
    <h2>Errol Spence Jr. vs Tim Tszyu</h2>
  </section>
  <section>
    <span>22 August 2026</span>
    <h2>Rolando Romero</h2><strong>VS</strong><h2>Teofimo Lopez</h2>
  </section>
</body></html>
"""


def test_all_agreed_promoters_are_registered():
    names = {spec.name for spec in OFFICIAL_SOURCES}
    assert names == {
        "Queensberry",
        "Top Rank",
        "The Ring / Riyadh Season",
        "Premier Boxing Champions",
        "Golden Boy",
        "BOXXER",
        "No Limit Boxing",
        "Zuffa Boxing",
    }


def test_generic_parser_handles_date_and_fight_layouts():
    spec = SourceSpec("Test Promoter", "https://example.com/events")
    events = parse_official_schedule(HTML, spec, date(2026, 7, 23))
    assert [(event.title, event.event_date.isoformat()) for event in events] == [
        ("Errol Spence Jr vs Tim Tszyu", "2026-07-25"),
        ("Rolando Romero vs Teofimo Lopez", "2026-08-22"),
    ]


def test_generic_parser_uses_json_ld_and_rejects_editorial_false_positives():
    html = """
    <script type="application/ld+json">
      {"@type":"SportsEvent","startDate":"2026-08-22T20:00:00-05:00",
       "name":"Rolando Romero vs Teofimo Lopez"}
    </script>
    <p>September 12, 2026</p>
    <h2>White provides frustrating update on Fury vs Joshua location</h2>
    """
    spec = SourceSpec("Test Promoter", "https://example.com/events")
    events = parse_official_schedule(html, spec, date(2026, 7, 28))
    assert [(event.title, event.event_date.isoformat()) for event in events] == [
        ("Rolando Romero vs Teofimo Lopez", "2026-08-22"),
    ]


def test_registered_source_parser_handles_split_names_and_numeric_date():
    spec = next(source for source in OFFICIAL_SOURCES if source.name == "Queensberry")
    html = """
    <article>
      <span>Moses</span><span>Itauma</span><strong>Vs</strong>
      <span>Filip</span><span>Hrgovic</span>
      <time>29 | 8 | 26</time>
      <a href="/pages/moses-itauma-vs-filip-hrgovic">Event Info</a>
    </article>
    """
    events = parse_official_schedule(html, spec, date(2026, 7, 28))
    assert ("Moses Itauma vs Filip Hrgovic", "2026-08-29") in [
        (event.title, event.event_date.isoformat()) for event in events
    ]


def test_ring_event_page_keeps_headline_and_rejects_undercards():
    spec = next(source for source in OFFICIAL_SOURCES if source.name == "The Ring / Riyadh Season")
    source_url = "https://www.ringmagazine.com/events/roach-vs-zepeda-card"
    event_date = date(2026, 8, 1)
    selected = select_main_events(
        [
            DiscoveredEvent(
                "Curiel vs Randall",
                event_date,
                source_url,
                card_role="main_event",
            ),
            DiscoveredEvent(
                "Lamont Roach Jr vs William Zepeda",
                event_date,
                source_url,
                card_role="main_event",
            ),
            DiscoveredEvent(
                "Muratalla vs Conceicao",
                event_date,
                source_url,
                card_role="main_event",
            ),
        ],
        spec,
    )
    assert [event.title for event in selected] == [
        "Lamont Roach Jr vs William Zepeda"
    ]


def test_pbc_prefers_card_level_fight_night_page():
    spec = next(source for source in OFFICIAL_SOURCES if source.name == "Premier Boxing Champions")
    event_date = date(2026, 9, 19)
    selected = select_main_events(
        [
            DiscoveredEvent(
                "Jesus Ramos vs Meiirim Nursultanov",
                event_date,
                "https://www.premierboxingchampions.com/jesus-ramos-vs-meiirim-nursultanov",
                card_role="main_event",
            ),
            DiscoveredEvent(
                "Isaac Cruz vs Nestor Bravo",
                event_date,
                "https://www.premierboxingchampions.com/fight-night-september-19-2026",
                card_role="main_event",
            ),
        ],
        spec,
    )
    assert [event.title for event in selected] == ["Isaac Cruz vs Nestor Bravo"]


def test_pbc_rejects_ambiguous_bout_pages_without_card_headline():
    spec = next(source for source in OFFICIAL_SOURCES if source.name == "Premier Boxing Champions")
    event_date = date(2026, 9, 19)
    selected = select_main_events(
        [
            DiscoveredEvent(
                "First Fighter vs First Challenger",
                event_date,
                "https://www.premierboxingchampions.com/first-fighter-vs-first-challenger",
                card_role="main_event",
            ),
            DiscoveredEvent(
                "Second Fighter vs Second Challenger",
                event_date,
                "https://www.premierboxingchampions.com/second-fighter-vs-second-challenger",
                card_role="main_event",
            ),
        ],
        spec,
    )
    assert selected == []


NO_LIMIT_DETAIL_HTML = """
<html>
  <head><title>Nikita Tszyu vs Ben Mahoney | No Limit Boxing</title></head>
  <body>
    <p>Two undefeated Australians go head-to-head on Wednesday, 26 August.</p>
    <time>Wednesday 26 August, 6:00PM AEST</time>
  </body>
</html>
"""


def test_no_limit_detail_parser_extracts_bout_and_date():
    event = parse_no_limit_event_detail(
        NO_LIMIT_DETAIL_HTML,
        "https://nolimitboxing.com.au/events/nikita-tszyu-vs-ben-mahoney",
        date(2026, 7, 28),
    )
    assert event is not None
    assert event.title == "Nikita Tszyu vs Ben Mahoney"
    assert event.event_date.isoformat() == "2026-08-26"


@patch("scripts.sources.official.requests.get")
def test_no_limit_fetch_follows_event_detail_links(mock_get):
    listing = """
    <a href="/events/nikita-tszyu-vs-ben-mahoney">
      Nikita Tszyu VS Ben Mahoney
    </a>
    """
    mock_get.side_effect = [
        Mock(status_code=200, text=listing),
        Mock(status_code=200, text=NO_LIMIT_DETAIL_HTML),
    ]
    spec = next(source for source in OFFICIAL_SOURCES if source.name == "No Limit Boxing")
    events = fetch_official_events(spec, today=date(2026, 7, 28))
    assert [(event.title, event.event_date.isoformat()) for event in events] == [
        ("Nikita Tszyu vs Ben Mahoney", "2026-08-26"),
    ]

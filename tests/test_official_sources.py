from datetime import date
from unittest.mock import Mock, patch

import pytest

from scripts.models import DiscoveredEvent
from scripts.sources.official import (
    OFFICIAL_SOURCES,
    OfficialSourceError,
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


# Markup from the redesigned public PBC schedule, October 24, 2026.
PBC_SCHEDULE_HTML = """
<div class="pbc-schedule__fight-inner">
  <div class="pbc-schedule__fight-when">
    <h4 class="pbc-schedule__date"><span><abbr title="Saturday">Sat</abbr>,</span>
      <span><abbr title="December">Dec</abbr></span> 5, 2026
      <span class="pbc-schedule__time">8PM <abbr title="Eastern Time">ET</abbr> /
        5PM <abbr title="Pacific Time">PT</abbr></span></h4>
    <div class="pbc-schedule__clock" data-countdown="2026-12-06T01:00:00.000Z"></div>
  </div>
  <div class="pbc-schedule__fight-what"><div class="pbc-schedule__card"><ul>
    <li><h2><a href="/bouts/255422"><span>David Benavidez</span>
      <em><abbr title="versus">vs</abbr></em> <span>Michal Cieslak</span></a></h2></li>
    <li><h2><a href="/bouts/809398"><span>Vergil Ortiz Jr.</span>
      <em><abbr title="versus">vs</abbr></em> <span>Keith Thurman</span></a></h2></li>
    <li><h2><a href="/bouts/783768"><span>Nikita Tszyu</span>
      <em><abbr title="versus">vs</abbr></em> <span>Opponent TBA</span></a></h2></li>
    <li class="pbc-schedule__arena">Desert Diamond Arena, Glendale, AZ</li>
    <li><a href="/events/391735" class="pbc-schedule__btn">View Fight Night</a></li>
  </ul></div></div>
</div>
"""


def test_redesigned_pbc_schedule_extracts_only_headline_and_venue_date():
    spec = next(s for s in OFFICIAL_SOURCES if s.name == "Premier Boxing Champions")
    events = parse_official_schedule(PBC_SCHEDULE_HTML, spec, date(2026, 10, 24))
    assert [(e.title, e.event_date, e.source_url, e.card_role) for e in events] == [
        ("David Benavidez vs Michal Cieslak", date(2026, 12, 5),
         "https://www.premierboxingchampions.com/events/391735", "main_event")
    ]
    assert parse_official_schedule(PBC_SCHEDULE_HTML, spec, date(2026, 12, 6)) == []


def test_redesigned_pbc_schedule_keeps_dates_scoped_to_each_card():
    spec = next(s for s in OFFICIAL_SOURCES if s.name == "Premier Boxing Champions")
    second = (PBC_SCHEDULE_HTML.replace("5, 2026", "12, 2026")
              .replace("391735", "999999").replace("David Benavidez", "Fighter Alpha")
              .replace("Michal Cieslak", "Fighter Beta"))
    events = parse_official_schedule(PBC_SCHEDULE_HTML + second, spec, date(2026, 10, 24))
    assert [(e.title, e.event_date) for e in events] == [
        ("David Benavidez vs Michal Cieslak", date(2026, 12, 5)),
        ("Fighter Alpha vs Fighter Beta", date(2026, 12, 12)),
    ]


def test_redesigned_pbc_schedule_does_not_promote_undercard_on_malformed_card():
    spec = next(s for s in OFFICIAL_SOURCES if s.name == "Premier Boxing Champions")
    for broken in [
        PBC_SCHEDULE_HTML.replace('/events/391735', '/bouts/255422'),
        PBC_SCHEDULE_HTML.replace('/events/391735', 'https://example.com/events/391735'),
        PBC_SCHEDULE_HTML.replace('David Benavidez', ''),
    ]:
        assert parse_official_schedule(broken, spec, date(2026, 10, 24)) == []


@patch("scripts.sources.official.http.get")
def test_pbc_fetch_uses_new_schedule_and_preserves_http_safety(mock_get):
    spec = next(s for s in OFFICIAL_SOURCES if s.name == "Premier Boxing Champions")
    mock_get.return_value = Mock(status_code=200, text=PBC_SCHEDULE_HTML)
    assert len(fetch_official_events(spec, date(2026, 10, 24))) == 1
    assert mock_get.call_args.args[0] == "https://www.premierboxingchampions.com/events/schedule"
    mock_get.return_value = Mock(status_code=403)
    with pytest.raises(OfficialSourceError, match="HTTP 403"):
        fetch_official_events(spec, date(2026, 10, 24))


def test_zuffa_bout_preview_is_not_a_standalone_main_event():
    spec = next(source for source in OFFICIAL_SOURCES if source.name == "Zuffa Boxing")
    html = """
    <article><time>September 12, 2026</time>
      <a href="/news/title-fight-preview-jai-opetaia-vs-noel-mikaelian">
        Jai Opetaia vs Noel Mikaelian
      </a>
    </article>
    <article><time>September 12, 2026</time>
      <a href="/news/ryan-garcia-vs-conor-benn-sept-12">Ryan Garcia vs Conor Benn</a>
    </article>
    """
    events = parse_official_schedule(html, spec, date(2026, 9, 10))
    assert [event.title for event in events] == ["Ryan Garcia vs Conor Benn"]
    assert select_main_events([
        DiscoveredEvent("Jai Opetaia vs Noel Mikaelian", date(2026, 9, 12),
                        "https://www.ufc.com/news/title-fight-preview-jai-opetaia-vs-noel-mikaelian",
                        card_role="main_event")
    ], spec) == []


def test_zuffa_memorabilia_auction_is_not_a_fight():
    spec = next(source for source in OFFICIAL_SOURCES if source.name == "Zuffa Boxing")
    html = """
    <article><time>October 1, 2026</time>
      <a href="/news/live-now-garcia-vs-benn-memorabilia-auction">
        Garcia vs Benn Memorabilia Auction
      </a>
    </article>
    <article><time>October 17, 2026</time>
      <a href="/events/dubois-vs-wardley">Daniel Dubois vs Fabio Wardley</a>
    </article>
    """
    events = parse_official_schedule(html, spec, date(2026, 10, 1))
    assert [event.title for event in events] == ["Daniel Dubois vs Fabio Wardley"]


BOXXER_HTML = """
<div class="elementor-widget-wrap">
  <h2><a href="/events/lauren-price-vs-michaela-kotaskova-20-november-2026-utilita-arena-cardiff/">Price vs Kotaskova</a></h2>
  <h4><a href="/events/boxxer-expands-into-the-netherlands/">UTILITA ARENA, CARDIFF</a></h4>
  <a href="/events/lauren-price-vs-michaela-kotaskova-20-november-2026-utilita-arena-cardiff/">20 NOV</a>
  <a href="https://tickets.boxxer.com/event-details/lauren-price">Buy Tickets</a>
</div>
<div class="elementor-widget-wrap">
  <h2><a href="/events/gradus-kraus-28-november-2026-amsterdam/">KRAUS VS DEINES</a></h2>
  <a href="/events/gradus-kraus-28-november-2026-amsterdam/">28 NOV</a>
</div>
<h2><a href="https://tickets.boxxer.com/event-details/fighter-a-vs-fighter-b">Fighter A vs Fighter B</a></h2>
"""


def test_boxxer_homepage_keeps_official_links_and_separate_event_dates():
    spec = next(s for s in OFFICIAL_SOURCES if s.name == "BOXXER")
    events = parse_official_schedule(BOXXER_HTML, spec, date(2026, 10, 24))
    assert [(e.title, e.event_date, e.source_url) for e in events] == [
        ("Price vs Kotaskova", date(2026, 11, 20),
         "https://www.boxxer.com/events/lauren-price-vs-michaela-kotaskova-20-november-2026-utilita-arena-cardiff/"),
        ("Kraus vs Deines", date(2026, 11, 28),
         "https://www.boxxer.com/events/gradus-kraus-28-november-2026-amsterdam/"),
    ]
    assert all(e.card_role == "main_event" for e in events)
    assert parse_official_schedule(BOXXER_HTML, spec, date(2026, 12, 1)) == []


def test_boxxer_uses_explicit_year_at_year_boundary():
    spec = next(s for s in OFFICIAL_SOURCES if s.name == "BOXXER")
    html = '<h2><a href="/events/price-vs-kotaskova-9-january-2027/">Price vs Kotaskova</a></h2>'
    events = parse_official_schedule(html, spec, date(2026, 12, 30))
    assert events[0].event_date == date(2027, 1, 9)


def test_boxxer_short_date_fallback_does_not_cross_card_boundaries():
    spec = next(s for s in OFFICIAL_SOURCES if s.name == "BOXXER")
    html = """
    <div class="elementor-widget-wrap">
      <h2><a href="/events/price-vs-kotaskova/">Price vs Kotaskova</a></h2>
      <span>20 NOV</span>
    </div>
    <div class="elementor-widget-wrap">
      <h2><a href="/events/kraus-vs-deines/">Kraus vs Deines</a></h2>
    </div>
    """
    events = parse_official_schedule(html, spec, date(2026, 10, 24))
    assert [(e.title, e.event_date) for e in events] == [
        ("Price vs Kotaskova", date(2026, 11, 20))
    ]
    ambiguous = html.replace('</div>\n    <div class="elementor-widget-wrap">', '')
    assert parse_official_schedule(ambiguous, spec, date(2026, 10, 24)) == []


@patch("scripts.sources.official.http.get")
def test_boxxer_fetch_uses_homepage_and_rejects_empty_ticket_shop(mock_get):
    spec = next(s for s in OFFICIAL_SOURCES if s.name == "BOXXER")
    mock_get.return_value = Mock(status_code=200, text=BOXXER_HTML)
    assert len(fetch_official_events(spec, date(2026, 10, 24))) == 2
    assert mock_get.call_args.args[0] == "https://www.boxxer.com/"
    mock_get.return_value = Mock(status_code=200, text="<title>Buy your tickets online now!</title>")
    with pytest.raises(OfficialSourceError, match="parsed 0"):
        fetch_official_events(spec, date(2026, 10, 24))


ZUFFA_HEADLINE_HTML = """
<div class="fifty-fifty__text-block">
  <h2 class="fifty-fifty__title">Billam-Smith vs Clarke</h2>
  <div class="fifty-fifty__body"><p>Zuffa Boxing returns to London's Copper Box Arena
    on Saturday, November 7, with an all-British cruiserweight main event.
    For Zuffa Boxing 12, former world champion Chris Billam-Smith faces Olympian Chev Clarke.</p></div>
  <div class="fifty-fifty__link"><a href="https://t.co/example">Get Tickets!</a></div>
</div>
<article><time>November 7, 2026</time>
  <a href="/news/title-fight-preview-bentley-vs-mosley">Bentley vs Mosley</a>
</article>
"""


def test_zuffa_headline_feature_discovers_event_without_fight_link():
    spec = next(s for s in OFFICIAL_SOURCES if s.name == "Zuffa Boxing")
    events = parse_official_schedule(ZUFFA_HEADLINE_HTML, spec, date(2026, 10, 24))
    assert [(e.title, e.event_date, e.source_url, e.card_role) for e in events] == [
        ("Billam-Smith vs Clarke", date(2026, 11, 7),
         "https://www.ufc.com/zuffaboxing", "main_event")
    ]
    assert parse_official_schedule(ZUFFA_HEADLINE_HTML, spec, date(2026, 11, 8)) == []


def test_zuffa_explicit_headline_takes_precedence_over_same_card_bout_articles():
    spec = next(s for s in OFFICIAL_SOURCES if s.name == "Zuffa Boxing")
    html = ZUFFA_HEADLINE_HTML + """
    <article><time>November 7, 2026</time>
      <a href="/news/bentley-vs-mosley-announced">Bentley vs Mosley</a>
    </article>
    <article><time>December 12, 2026</time>
      <a href="/news/fighter-alpha-vs-fighter-beta-announced">Fighter Alpha vs Fighter Beta</a>
    </article>
    """
    events = parse_official_schedule(html, spec, date(2026, 10, 24))
    assert [(e.title, e.event_date) for e in events] == [
        ("Billam-Smith vs Clarke", date(2026, 11, 7)),
        ("Fighter Alpha vs Fighter Beta", date(2026, 12, 12)),
    ]


@pytest.mark.parametrize("html", [
    ZUFFA_HEADLINE_HTML.replace("cruiserweight main event", "cruiserweight interview"),
    ZUFFA_HEADLINE_HTML.replace("Saturday, November 7", "a future date"),
    ZUFFA_HEADLINE_HTML.replace("Billam-Smith vs Clarke</h2>", "Billam-Smith vs Clarke highlights</h2>"),
])
def test_zuffa_ambiguous_or_editorial_features_are_not_staged(html):
    spec = next(s for s in OFFICIAL_SOURCES if s.name == "Zuffa Boxing")
    assert parse_official_schedule(html, spec, date(2026, 10, 24)) == []


@patch("scripts.sources.official.http.get")
def test_zuffa_fetch_reads_feature_and_keeps_empty_response_safety(mock_get):
    spec = next(s for s in OFFICIAL_SOURCES if s.name == "Zuffa Boxing")
    mock_get.return_value = Mock(status_code=200, text=ZUFFA_HEADLINE_HTML)
    assert len(fetch_official_events(spec, date(2026, 10, 24))) == 1
    mock_get.return_value = Mock(status_code=200, text="<h2>Zuffa Boxing Featured Content</h2>")
    with pytest.raises(OfficialSourceError, match="parsed 0"):
        fetch_official_events(spec, date(2026, 10, 24))


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


@patch("scripts.sources.official.http.get")
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

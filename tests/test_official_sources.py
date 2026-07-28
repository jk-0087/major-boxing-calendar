from datetime import date

from scripts.sources.official import OFFICIAL_SOURCES, SourceSpec, parse_official_schedule


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
        "Tasman Fighters",
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

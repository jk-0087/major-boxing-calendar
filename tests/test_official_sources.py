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

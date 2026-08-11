from scripts.summarize_discovery import render_summary


def test_discovery_summary_reports_health_and_counts():
    summary = render_summary(
        {
            "checked_at": "2026-08-11T12:00:00+10:00",
            "sources": [
                {
                    "source": "Matchroom",
                    "status": "ok",
                    "events": 5,
                },
                {
                    "source": "Optional Source",
                    "status": "skipped",
                    "error": "HTTP 403",
                },
            ],
            "changes": [],
            "current_unmatched": [{"title": "A vs B"}],
            "staged": [{"title": "A vs B"}, {"title": "C vs D"}],
        }
    )
    assert "| Matchroom | ok | 5 |" in summary
    assert "| Optional Source | skipped | — | HTTP 403 |" in summary
    assert "New unmatched this run: **1**" in summary
    assert "Total staged after safe merge: **2**" in summary

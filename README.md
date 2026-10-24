# Major Boxing Calendar

The live source of truth is `data/events.json`. Every six hours, GitHub Actions checks trusted boxing schedules.

[Website](https://jk-0087.github.io/major-boxing-calendar/) · [Subscription feed](https://jk-0087.github.io/major-boxing-calendar/major-boxing-calendar.ics)

## Sources

- **Matchroom Boxing**
- **Queensberry Promotions**
- **Top Rank**
- **The Ring / Riyadh Season** — supplementary aggregate discovery only
- **Premier Boxing Champions (PBC)**
- **Golden Boy Promotions**
- **BOXXER**
- **Most Valuable Promotions (MVP)**
- **No Limit Boxing**
- **Zuffa Boxing**

Every source is isolated: independent checks run concurrently, while expected HTTP errors, timeouts, blocking, or suspicious parser results are logged and skipped without failing the workflow. Unexpected programming errors still fail the workflow. A failed source never causes existing calendar events or its staged future proposals to be deleted or cleared. Expired proposals are removed independently; approved historical events are retained.

The Ring reads the site's public structured upcoming schedule, selecting only explicitly marked main events. Direct sources take priority for overlapping cards. Ring-only discoveries go to staging for manual inclusion review; The Ring never automatically modifies approved events or their times. Incomplete, empty, or ambiguous schedule responses are safely skipped.

Ring main events at flyweight (112 lb) or lighter are excluded. Super flyweight/junior bantamweight and higher divisions remain eligible for review. Unknown divisions remain review leads; undercard weights do not exclude a qualifying headline card. This filter does not change approved events or direct-source discovery.

## Automatic behavior

- strongly matches official listings to existing fights
- preserves every existing UID
- compares each revision with the previous Git version to reject deletions, UID changes, and missing `SEQUENCE` increments
- uses `main_card_start` as the calendar event start (`DTSTART`); ring-walk estimates remain description-only
- publishes `DTSTART` as a fixed UTC instant so calendar apps reliably display it in the subscriber's timezone
- records a named IANA timezone for each known venue and includes both Sydney and venue-local start times in event details
- treats source dates as venue-local references and never rewrites an Australian broadcast datetime from date-only discovery
- increments `SEQUENCE` only when a meaningful field changes
- regenerates `major-boxing-calendar.ics` and `index.html` after safe matched updates; the build workflow also keeps both generated files current after relevant pushes
- orders cards by their actual start instant, not their venue-local date string; calendar descriptions use UTF-8-safe iCalendar line folding
- removes completed cards from the website after their estimated finish, while retaining them in the subscription feed and source data
- never deletes events because a source item disappears
- stages unmatched main events in `data/proposed-events.json` instead of publishing them automatically; undercard bouts are rejected
- publishes a source-health summary and downloadable discovery report with each automated run, including check duration, last successful check and consecutive failures

## Workflow

`.github/workflows/auto-update-calendar.yml` runs every six hours and can also be run manually from GitHub Actions.

Both build and discovery workflows validate, generate, test, commit safe output changes, and upload only `index.html` and `major-boxing-calendar.ics` for the shared `deploy-pages.yml` workflow. Deployment does not depend on a bot commit triggering another build. Builds and scheduled updates share a writer queue to prevent competing commits and deployments. If a push fails, deployment stops rather than publishing uncommitted results.

One-time rollout: after these workflows are on `main`, set **Settings → Pages → Build and deployment → Source → GitHub Actions**, then run **Build and Publish Calendar**. Keep the existing branch-based publishing setting until the new workflows have been pushed. The site and subscription URLs do not change. See [GitHub's custom Pages workflow documentation](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).

Source-health history is cached separately from the calendar data; it never changes event verification timestamps or revision numbers. Cache eviction resets historical streaks, but does not affect discovery safety. Each run's report is retained for 14 days. Source adapters reuse connections within each worker and retry only bounded transient failures; HTTP 403 is not retried. PBC, BOXXER and Zuffa have dedicated parsers, with shared parsing primitives kept independent of the adapter registry.

## Local checks and discovery previews

```sh
python -m pip install -r requirements.txt -r requirements-dev.txt
python scripts/validate.py --previous-ref HEAD
python -m pytest -q
python scripts/generate.py
```

Tests generate their own outputs with fixed reference times instead of relying on committed website files or the wall clock. For reproducible generation, use `--now 2026-10-24T12:00:00+11:00` or set `MBC_NOW`.

```sh
# Read-only preview; only the explicitly requested report is written.
python scripts/discover.py --report /tmp/boxing-preview.json

# Apply safe matched updates and replace the staged queue using source safety rules.
python scripts/discover.py --apply --report /tmp/boxing-discovery.json
```

Discovery exits with `10` when approved events changed, `0` otherwise; other exit codes indicate failure. Date-only discoveries never supply or change broadcast start times. New events, cancellations and verified detail/time changes require review.

## Approving and maintaining events

`scripts/maintain.py` previews by default. Supply a JSON details file containing verified fields and a short change note. Add `--apply` only after reviewing the preview. It validates the complete result and renders outputs before saving. It never commits or pushes.

```sh
# Approve one staged MAIN EVENT, selected by its exact staged source URL.
python scripts/maintain.py approve 'https://promoter.example/events/card/' \
  --details /tmp/verified-card.json --note 'Approved official headline card'

# Update selected fields of an existing approved event by its stable UID.
python scripts/maintain.py update 'EXISTING-UID' \
  --details /tmp/verified-update.json --note 'Official venue announced' --apply
```

Approval details must contain `title`, `fighters`, `status`, `promotion`, `titles`, `venue` (including IANA `timezone` for a known city), `broadcast.australia`, `main_card`, `main_card_start`, `end`, and `ring_walk`. Use the existing approved structure as a template, without `uid`, `sequence` or `history`. Sources include `url`, `publisher` and timezone-aware `checked_at`; staged provenance is retained automatically. `main_card_start` and `end` require timezone-aware ISO timestamps with `confirmed` or `estimated` confidence. Unknown ring walks may use `null` with `tba` confidence. Never use a ring walk as the main-card start.

Updates accept partial nested fields, for example `{"venue": {"name": "Official arena name"}}`. The command preserves UIDs, increments sequence/history exactly once for an actual change, refreshes verification on the primary source, and leaves no-op updates unchanged. Approvals generate a new stable UID and initial history entry and remove only the selected proposal. Identity/history fields cannot be supplied manually. Review the resulting data and generated-file differences, then commit and push intentionally.

# Major Boxing Calendar

The live source of truth is `data/events.json`. Every six hours, GitHub Actions checks trusted boxing schedules.

## Sources

- **Matchroom Boxing**
- **Queensberry Promotions**
- **Top Rank**
- **The Ring / Riyadh Season**
- **Premier Boxing Champions (PBC)**
- **Golden Boy Promotions**
- **BOXXER**
- **Most Valuable Promotions (MVP)**
- **No Limit Boxing**
- **Zuffa Boxing**

Every source is isolated: HTTP errors, timeouts, blocking, or suspicious parser results are logged and skipped without failing the workflow. A failed source never causes existing calendar events to be deleted or cleared.

## Automatic behavior

- strongly matches official listings to existing fights
- preserves every existing UID
- uses `main_card_start` as the calendar event start (`DTSTART`); ring-walk estimates remain description-only
- publishes `DTSTART` as a fixed UTC instant so calendar apps reliably display it in the subscriber's timezone
- records a named IANA timezone for each known venue and includes both Sydney and venue-local start times in event details
- treats source dates as venue-local references and never rewrites an Australian broadcast datetime from date-only discovery
- increments `SEQUENCE` only when a meaningful field changes
- regenerates `major-boxing-calendar.ics` and `index.html` after safe matched updates; the build workflow also keeps both generated files current after relevant pushes
- never deletes events because a source item disappears
- stages unmatched main events in `data/proposed-events.json` instead of publishing them automatically; undercard bouts are rejected

## Workflow

`.github/workflows/auto-update-calendar.yml` runs every six hours and can also be run manually from GitHub Actions.

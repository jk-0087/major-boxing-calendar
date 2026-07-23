# Major Boxing Calendar — automatic update build

The live source of truth is `data/events.json`. Every six hours, GitHub Actions checks official boxing schedules.

## Sources

- **Matchroom Boxing:** primary source
- **DAZN:** optional schedule source
- **Queensberry Promotions**
- **Top Rank**
- **The Ring / Riyadh Season**
- **Premier Boxing Champions (PBC)**
- **Golden Boy Promotions**
- **BOXXER**
- **Most Valuable Promotions (MVP)**
- **No Limit Boxing**
- **Tasman Fighters**
- **Zuffa Boxing**

Every source is isolated: HTTP errors, timeouts, blocking, or suspicious parser results are logged and skipped without failing the workflow or changing the existing calendar.

If Matchroom or DAZN cannot be fetched—or returns suspiciously few events—the source is skipped and `events.json` remains unchanged. A run with no usable sources completes as a safe no-change result.

## Automatic behavior

- strongly matches official listings to existing fights
- preserves every existing UID
- updates a matched event date and shifts its stored finish/ring-walk times by the same number of days
- increments `SEQUENCE` only when a meaningful field changes
- regenerates `major-boxing-calendar.ics` and `index.html` only when safe changes are applied
- never deletes events because a source item disappears
- stages unmatched fights in `data/proposed-events.json` instead of publishing them automatically

## Workflow

`.github/workflows/auto-update-calendar.yml` runs every six hours and can also be run manually from GitHub Actions.

## Local commands

```bash
python -m pip install -r requirements.txt -r requirements-dev.txt
python scripts/discover.py          # dry run
python scripts/discover.py --apply  # apply safe matched changes
python scripts/validate.py
python scripts/generate.py
pytest -q
```

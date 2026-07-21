# Major Boxing Calendar — automatic update build

The live source of truth is `data/events.json`. Every six hours, GitHub Actions checks the official DAZN boxing schedule.

## Automatic behavior

- strongly matches DAZN listings to existing fights
- preserves every existing UID
- updates a matched event date and shifts its stored finish/ring-walk times by the same number of days
- increments `SEQUENCE` only when a meaningful field changes
- regenerates `major-boxing-calendar.ics` and `index.html` only when safe changes are applied
- never deletes events because a source item disappears
- stops if the DAZN parser returns suspiciously few results
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

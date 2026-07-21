# Major Boxing Calendar v4

`data/events.json` is the source of truth.

## Generated files

- `major-boxing-calendar.ics`
- `index.html`

## Workflows

- `build-calendar.yml` validates, tests, generates, and commits generated files.
- `discover-updates.yml` runs a review-first discovery placeholder and opens a pull request only when proposed data changes.

## Install

Upload the repository contents while preserving folders, then run
**Build and Publish Calendar** from the GitHub Actions tab.

The discovery component is deliberately review-first. It does not publish
unverified fight data directly to subscribers.

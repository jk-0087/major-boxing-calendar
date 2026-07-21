# Major Boxing Calendar v4

Review-first GitHub Pages automation.

- Source of truth: `data/events.json`
- Generated outputs: `major-boxing-calendar.ics` and `index.html`
- Build workflow validates, tests, generates and commits changes.
- Discovery workflow creates a review pull request.

The discovery script is deliberately a safe placeholder. It does not publish unreviewed scraped data.

Upload the repository contents while preserving folders, then run **Build and Publish Calendar** from the Actions tab.

#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


def render_summary(report: dict) -> str:
    lines = [
        "## Boxing source health",
        "",
        f"Checked: `{report['checked_at']}`",
        "",
        "| Source | Status | Events | Detail |",
        "| --- | --- | ---: | --- |",
    ]
    for source in report["sources"]:
        detail = str(
            source.get("error", source.get("proposal_policy", ""))
        ).replace("\n", "<br>").replace("|", "\\|")
        lines.append(
            f"| {source['source']} | {source['status']} | "
            f"{source.get('events', '—')} | {detail} |"
        )
    lines.extend(
        [
            "",
            f"Matched changes: **{len(report['changes'])}**  ",
            f"New unmatched this run: **{len(report['current_unmatched'])}**  ",
            f"Total staged after safe merge: **{len(report['staged'])}**",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: summarize_discovery.py REPORT.json")
    path = Path(sys.argv[1])
    if not path.exists():
        print("## Boxing source health\n\nDiscovery report was not produced.")
        return 0
    report = json.loads(path.read_text(encoding="utf-8"))
    print(render_summary(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

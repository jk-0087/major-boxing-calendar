#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
proposal_file = ROOT / "data/proposed-events.json"

if not proposal_file.exists():
    proposal_file.write_text("[]\n", encoding="utf-8")

print("Discovery placeholder completed. No live event data was changed.")

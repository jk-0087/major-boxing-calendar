import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_validation_and_generation():
    subprocess.run([sys.executable, str(ROOT / "scripts/validate.py")], check=True)
    subprocess.run([sys.executable, str(ROOT / "scripts/generate.py")], check=True)

    events = json.loads((ROOT / "data/events.json").read_text(encoding="utf-8"))
    calendar = (ROOT / "major-boxing-calendar.ics").read_text(encoding="utf-8")
    website = (ROOT / "index.html").read_text(encoding="utf-8")

    assert calendar.count("BEGIN:VEVENT") == len(events)
    assert "X-WR-CALNAME:Major Boxing Calendar" in calendar
    assert website.count('class="event"') == len(events)

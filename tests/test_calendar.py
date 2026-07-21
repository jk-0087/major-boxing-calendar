import json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def test_validation_and_generation():
    subprocess.run([sys.executable,str(ROOT/'scripts/validate.py')],check=True)
    subprocess.run([sys.executable,str(ROOT/'scripts/generate.py')],check=True)
    text=(ROOT/'major-boxing-calendar.ics').read_text(encoding='utf-8')
    events=json.loads((ROOT/'data/events.json').read_text(encoding='utf-8'))
    assert text.count('BEGIN:VEVENT') == len(events)
    assert 'X-WR-CALNAME:Major Boxing Calendar' in text

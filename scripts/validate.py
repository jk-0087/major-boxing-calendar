#!/usr/bin/env python3
import json
from datetime import datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
events=json.loads((ROOT/'data/events.json').read_text(encoding='utf-8'))
uids=set(); errors=[]
for i,e in enumerate(events,1):
    if e['uid'] in uids: errors.append(f'Event {i}: duplicate UID')
    uids.add(e['uid'])
    if ' vs ' not in e['title']: errors.append(f"Event {i}: title must use ' vs '")
    if e['title'] != f"{e['fighters']['red']} vs {e['fighters']['blue']}": errors.append(f'Event {i}: title and fighter names differ')
    for field in ('start','end','ring_walk'):
        value=e[field]['value']
        if value:
            try: datetime.fromisoformat(value)
            except ValueError: errors.append(f'Event {i}: invalid {field} datetime')
    if datetime.fromisoformat(e['end']['value']) <= datetime.fromisoformat(e['start']['value']): errors.append(f'Event {i}: end must be after start')
    versions=[x['version'] for x in e['history']]
    if versions != sorted(set(versions)): errors.append(f'Event {i}: history versions must be unique and ordered')
    if e['sequence'] < max(versions): errors.append(f'Event {i}: sequence below history version')
if errors: raise SystemExit('\n'.join(errors))
print(f'Validated {len(events)} events.')

#!/usr/bin/env python3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
output=ROOT/'data/proposed-events.json'
if not output.exists(): output.write_text('[]\n',encoding='utf-8')
print('Discovery placeholder completed. Review proposed-events.json before merging.')

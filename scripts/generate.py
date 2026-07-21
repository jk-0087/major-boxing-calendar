#!/usr/bin/env python3
from __future__ import annotations
import html,json
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
events=json.loads((ROOT/'data/events.json').read_text(encoding='utf-8'))
events.sort(key=lambda e:e['start']['value'])
def esc(v): return v.replace('\\','\\\\').replace('\n','\\n').replace(',','\\,').replace(';','\\;')
def dt(v): return datetime.fromisoformat(v)
def utc(v): return dt(v).astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
def friendly(obj):
    if not obj['value']: return 'TBA'
    return dt(obj['value']).strftime('%-I:%M %p, %a %-d %b %Y') + f" ({obj['confidence'].title()})"
lines=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//Major Boxing Calendar v4//jk-0087//EN','CALSCALE:GREGORIAN','METHOD:PUBLISH','X-WR-CALNAME:Major Boxing Calendar','X-WR-TIMEZONE:Australia/Sydney','X-WR-CALDESC:Curated major professional boxing events in Australian Eastern Time.','REFRESH-INTERVAL;VALUE=DURATION:PT12H','X-PUBLISHED-TTL:PT12H']
cards=[]
for e in events:
    checked=max(s['checked_at'] for s in e['sources']); stamp=dt(checked).astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    desc=(f"Status\n{e['status']}\n\nPromotion\n{', '.join(e['promotion'])}\n\nCity\n{e['venue']['city']}\n\nCountry\n{e['venue']['country']}\n\nTitles\n"+'\n'.join(e['titles'])+f"\n\nAustralia\n{e['broadcast']['australia']}\n\nMain Card\n{friendly(e['start'])}\n\nEstimated Finish\n{friendly(e['end'])}\n\nRing Walk\n{friendly(e['ring_walk'])}\n\nMain Card\n"+'\n'.join(e['main_card'])+f"\n\nOfficial / Schedule Source\n{e['sources'][0]['url']}\n\nVerified\n{dt(checked).strftime('%d %b %Y, %-I:%M %p')}")
    lines += ['BEGIN:VEVENT',f"UID:{e['uid']}",f'DTSTAMP:{stamp}',f'LAST-MODIFIED:{stamp}',f"SEQUENCE:{e['sequence']}",f"DTSTART:{utc(e['start']['value'])}",f"DTEND:{utc(e['end']['value'])}",f"SUMMARY:{esc(e['title'])}",f"LOCATION:{esc(e['venue']['name'])}",f'DESCRIPTION:{esc(desc)}',f"URL:{e['sources'][0]['url']}",'STATUS:CONFIRMED','TRANSP:TRANSPARENT','END:VEVENT']
    cards.append(f"<article class='event'><div class='date'>{dt(e['start']['value']).strftime('%-d %b')}</div><div><h2>{html.escape(e['title'])}</h2><p>{html.escape(e['venue']['name'])} · {html.escape(e['venue']['city'])}</p><p><strong>{html.escape(e['status'])}</strong> · {html.escape(e['broadcast']['australia'])}</p></div></article>")
lines.append('END:VCALENDAR')
(ROOT/'major-boxing-calendar.ics').write_text('\r\n'.join(lines)+'\r\n', encoding='utf-8')
page="""<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Major Boxing Calendar</title><style>body{font-family:system-ui,-apple-system,sans-serif;max-width:820px;margin:0 auto;padding:32px 20px;line-height:1.5}header{margin-bottom:36px}.event{display:grid;grid-template-columns:72px 1fr;gap:18px;padding:20px 0;border-top:1px solid #ddd}.date{font-weight:700;font-size:1.1rem}h2{font-size:1.2rem;margin:0 0 6px}p{margin:4px 0;color:#444}.button{display:inline-block;padding:11px 16px;border:1px solid #111;border-radius:8px;text-decoration:none;color:#111}</style></head><body><header><h1>Major Boxing Calendar</h1><p>Curated major professional boxing events with Australian times and broadcast details.</p><a class='button' href='major-boxing-calendar.ics'>Subscribe / Download</a></header><main>"""+''.join(cards)+"</main></body></html>"
(ROOT/'index.html').write_text(page, encoding='utf-8')
print(f'Generated {len(events)} events, calendar and website.')

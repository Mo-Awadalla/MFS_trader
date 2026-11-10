"""Join fresh quote availability to original official-opening and degraded-day gates."""
import json
from collections import Counter
import pandas as pd
from research_scout import audit_leveraged_etf_post_open_simplex_v49 as v49
from research_scout.reconcile_quote_blockers_20260907 import OUT, SYMBOLS, save

quotes=json.loads((OUT/'local_exact_targets.json').read_text())
openings,integrity=v49.load_openings()
old=v49.shared.load_json(v49.shared.AUDIT)
excluded=set(old['degraded_dates']['ARCX.PILLAR'])|set(old['degraded_dates']['EQUS.MINI'])
report={}
for clock in ['09:30:01','09:30:05']:
    counts=Counter(); passed=[]
    for row in quotes['rows']:
        day=row['date']; states=row['targets'][clock]
        if day in excluded: counts['degraded_day']+=1;continue
        op=openings.get(day,{})
        if not all(s in op for s in SYMBOLS): counts['incomplete_official_open']+=1;continue
        if len(states)!=6: counts['incomplete_quotes']+=1;continue
        if max(s['event_wait_seconds'] for s in states.values())>5: counts['event_wait_over_5s']+=1;continue
        ts=[pd.Timestamp(s['event_time']) for s in states.values()]
        if (max(ts)-min(ts)).total_seconds()>5:counts['event_span_over_5s']+=1;continue
        boundary=pd.Timestamp(f'{day} 09:31:00',tz='America/New_York')
        times=[pd.Timestamp(s['receive_time']) for s in states.values()]+[pd.Timestamp(op[s]['ts_recv']) for s in SYMBOLS]
        if any(t>=boundary for t in times): counts['not_observable_before_0931']+=1;continue
        passed.append(day)
    report[clock]={'passed_prerequisites':len(passed),'exclusions':dict(counts),'passed_dates':passed}
save('v49_observability.json',{'scope':'2023 existing MBP-1 only. Original official-open uniqueness, degraded-date, event-wait, event-span and receive-boundary requirements. Does not compute rolling features, stability, signals, or P&L.','sessions':quotes['sessions'],'observations':report,'statistics_integrity':integrity})
print(json.dumps({k:{x:y for x,y in v.items() if x!='passed_dates'} for k,v in report.items()},indent=2))

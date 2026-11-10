"""Read-only extraction of research decisions; never computes strategy returns."""
from pathlib import Path
import json
import re
import hashlib

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'research_scout/postmortem_20260907'

def read(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))

def compact(obj, depth=0):
    if depth > 5:
        return '<nested>'
    if isinstance(obj, dict):
        return {k: compact(v, depth+1) for k,v in obj.items()
                if not re.search(r'^(trades|signals|daily_returns|equity_curve|features|snapshots|events|rows|sessions|per_trade|fold_results)$', k) or not isinstance(v,(list,dict))}
    if isinstance(obj, list):
        if all(isinstance(x,(str,int,float,bool,type(None))) for x in obj):
            return obj if len(obj)<45 else obj[:3]+[f'<{len(obj)} items>']
        return [compact(x,depth+1) for x in obj[:4]] + ([f'<{len(obj)} items>'] if len(obj)>4 else [])
    return obj

def main():
    OUT.mkdir(exist_ok=True)
    files = sorted((ROOT/'research_scout').glob('*.json'))
    files += sorted((ROOT/'experiments').glob('*/metadata.json'))
    files += sorted((ROOT/'experiments').glob('*/validation/report.json'))
    files += sorted((ROOT/'experiments').glob('*/results.json'))
    files += sorted((ROOT/'data/parquet').glob('**/report.json'))
    files += sorted((ROOT/'external_artifacts/pysystemtrade_futures_data').glob('**/*report*.json'))
    files += sorted((ROOT/'docs/reports').glob('*.json'))
    files += sorted((ROOT/'research_scout/daytrade_batch_v83_v92').glob('specification.json'))
    files += sorted((ROOT/'research_scout/daytrade_batch_v83_v92/artifacts').glob('*.json'))
    docs = sorted((ROOT/'research_scout').glob('*.md'))
    docs += sorted((ROOT/'experiments').glob('*/validation/report.md'))
    docs += sorted((ROOT/'data/parquet').glob('**/report.md'))
    docs += sorted((ROOT/'docs').glob('**/*.md'))
    docs += sorted((ROOT/'research_scout/daytrade_batch_v83_v92/artifacts').glob('*.md'))
    inventory=[]; digest={}; errors=[]
    for p in files+docs:
        raw=p.read_bytes(); rel=p.relative_to(ROOT).as_posix()
        inventory.append(dict(path=rel,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
        if p.suffix=='.json':
            try: digest[rel]=compact(read(p))
            except Exception as e: errors.append(dict(path=rel,error=str(e)))
    (OUT/'source_manifest.json').write_text(json.dumps(dict(files=inventory,errors=errors),indent=2),encoding='utf-8')
    (OUT/'evidence_digest.json').write_text(json.dumps(digest,indent=2),encoding='utf-8')
    index=[]
    for rel,v in digest.items():
        if not isinstance(v,dict): continue
        index.append({'path':rel,'keys':list(v),'status':{k:val for k,val in v.items() if isinstance(val,(str,bool)) and re.search('status|decision|verdict|name|label|recommend|conclusion',k)},'children':{k:list(val) for k,val in v.items() if isinstance(val,dict) and k in ['candidates','hypotheses','results','development','holdout','gates','metrics','summary']}})
    (OUT/'evidence_index.json').write_text(json.dumps(index,indent=2),encoding='utf-8')
    print(json.dumps({'sources':len(inventory),'json_files':len(digest),'errors':errors}))

if __name__=='__main__': main()

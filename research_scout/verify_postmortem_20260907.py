"""Check ledger completeness against recorded result containers and source hashes."""
from pathlib import Path
import json, re, hashlib
from collections import Counter
from build_postmortem_20260907 import ROOT, OUT, read

def main():
    rows=read(OUT/'hypothesis_ledger.json'); ids={r['id'] for r in rows}
    assert len(ids)==len(rows), 'Duplicate record IDs'
    versions={int(m[1]) for r in rows if (m:=re.match(r'^V(\d+)(:|$)',r['id']))}
    assert versions==set(range(1,93)),sorted(set(range(1,93))-versions)
    covered={s for r in rows for s in r['sources']}
    assert all((ROOT/s).is_file() for s in covered)
    missing=[]; result_children=0
    for p in (ROOT/'research_scout').glob('*results_v*.json'):
        if not p.name.startswith(('upro_','spy_sh_')):continue
        m=re.search(r'_v(\d+)\.json$',p.name)
        if not m or int(m[1])>12:continue
        v=read(p)
        if not isinstance(v.get('candidates'),dict):continue
        tag='SPY-SH' if p.name.startswith('spy_sh') else 'V'+m[1]
        for child in v['candidates']:
            result_children+=1
            if f'{tag}:{child}' not in ids:missing.append(f'{tag}:{child}')
    assert not missing,missing
    formal=list((ROOT/'experiments').glob('*/metadata.json'))
    assert all('EXP:'+p.parent.name in ids for p in formal)
    manifest=read(OUT/'source_manifest.json')
    before={x['path']:x for x in manifest['files']}
    changed=[]
    for s in covered:
        raw=(ROOT/s).read_bytes(); digest=hashlib.sha256(raw).hexdigest()
        if s in before and before[s]['sha256']!=digest:changed.append(s)
        if s not in before:manifest['files'].append(dict(path=s,bytes=len(raw),sha256=digest))
    assert not changed,changed
    (OUT/'source_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
    # Reruns and sweeps are provenance, not extra independent hypotheses.
    sweeps=[]
    for p in (ROOT/'experiments').glob('*/validation/report.json'):
        v=read(p);dsr=v.get('gauntlet',{}).get('dsr') or {}
        sweep_rows=v.get('sweep_rows',[])
        sweeps.append(dict(experiment=p.parent.parent.name,source=p.relative_to(ROOT).as_posix(),
            reported_m_raw=dsr.get('m_raw'),reported_m_eff=dsr.get('m_eff'),
            stored_sweep_rows=len(sweep_rows) if isinstance(sweep_rows,(list,dict)) else sweep_rows,failure_reasons=v.get('gauntlet',{}).get('failure_reasons',[])))
    (OUT/'formal_sweep_exposure.json').write_text(json.dumps(sweeps,indent=2),encoding='utf8')
    result={'passed':True,'ledger_records':len(rows),'numbered_versions_covered':len(versions),
        'expanded_batch_children_covered':result_children,'formal_metadata_instances_covered':len(formal),
        'linked_source_files':len(covered),'manifest_files':len(manifest['files']),
        'source_hash_changes_during_audit':changed,'missing_expanded_children':missing,
        'new_strategy_returns_computed':False,'new_market_data_acquired':False,
        'limits':['Artifact reconciliation, not a rerun of all historical engines.','No formal claim of 232 independent tests.','Literature-only examples and uninstantiated strategy factories are not counted as completed hypotheses.','Recorded parameter sweeps remain in source reports and the sweep-exposure appendix, not separate independent ledger hypotheses.']}
    (OUT/'coverage_verification.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps(result))

if __name__=='__main__':main()

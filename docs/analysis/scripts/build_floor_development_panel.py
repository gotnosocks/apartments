"""Freeze a seeded coverage panel for repeated floor-feature source review."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path

from apartments.bayesian_evidence import load_evidence
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle

SEED=20260919
BANDS=('1-2','3-5','6-9','10-19','20+')
STATES=('yes','no','unknown')


def rank(kind, identity):
    return hashlib.sha256(f'{SEED}|{kind}|{identity}'.encode()).hexdigest()


def cell(row):
    floor=row.get('listed_floor')
    if floor is None: floor=row.get('advertised_floor')
    if floor is None or floor < 1: return None
    band=next((name for bound,name in ((2,'1-2'),(5,'3-5'),(9,'6-9'),(19,'10-19')) if floor<=bound),'20+')
    elevator=row.get('elevator')
    return band, 'yes' if elevator is True else 'no' if elevator is False else 'unknown'


def select(rows):
    """One seeded source observation per distinct unit, then two units per cell."""
    units=defaultdict(list)
    for row in rows:
        if cell(row) is not None: units[row['unit_id']].append(row)
    groups=defaultdict(list)
    for unit,values in units.items():
        chosen=min(values,key=lambda r:(rank('observation',r['audit_id']),r['audit_id']))
        groups[cell(chosen)].append(chosen)
    selected=[]; counts={}
    for band in BANDS:
        for state in STATES:
            candidates=sorted(groups[band,state],key=lambda r:(rank('unit',r['unit_id']),r['unit_id']))
            chosen=[]; buildings=set()
            for row in candidates:
                if row['building'] not in buildings:
                    chosen.append(row);buildings.add(row['building'])
                    if len(chosen)==2:break
            if len(chosen)<2:
                chosen+= [r for r in candidates if r not in chosen][:2-len(chosen)]
            selected.extend(chosen)
            counts[band+'|'+state]={'eligible_distinct_units':len(candidates),'selected':len(chosen),
                'selected_distinct_buildings':len({r['building'] for r in chosen})}
    return selected,counts


def run(dataset,evidence,output):
    dataset=Path(dataset); evidence=Path(evidence)
    manifest, files=_verified_bundle(dataset,retain={'observations.jsonl','floor-label-projection.jsonl'})
    rows=[json.loads(l) for l in files['observations.jsonl'].decode().split('\n') if l]
    chosen,counts=select(rows)
    ids={r['audit_id'] for r in chosen}
    label_changes={r['audit_id']:c for r,c in zip(rows,(json.loads(l) for l in files['floor-label-projection.jsonl'].decode().split('\n') if l),strict=True) if r['audit_id'] in ids}
    mapping=load_evidence(dataset,evidence)
    cases=[]
    for row in chosen:
        cases.append({'panel_cell':'|'.join(cell(row)), 'observation':row,
            'capture_label_evidence':label_changes[row['audit_id']]['captures'],
            'building_floor_evidence':manifest['building_floor_evidence'].get(row['building'],[]),
            'descriptions':mapping[row['audit_id']]})
    metadata={'version':'floor-source-development-panel-v1','seed':SEED,
        'dataset_manifest_sha256':digest(dataset/'complete.json'),'evidence_manifest_sha256':digest(evidence/'complete.json'),
        'policy':'Known model-floor rows only; choose one source observation per unit by seeded SHA256, then two distinct units per floor-band/elevator-state cell by seeded SHA256. Prefer distinct buildings within cell; reuse building only when fewer than two buildings eligible. No residuals or prices used. Frozen source review and repeated descriptive checks; not a representative population sample or validation holdout.',
        'cells':counts,'selected_units':len(chosen)}
    return publish_bundle(output,{'cases.jsonl':''.join(canonical(c)+'\n' for c in cases),
        'selection.json':canonical([{k:r[k] for k in ('audit_id','unit_id','source_listing_id','building')}|{'cell':'|'.join(cell(r))} for r in chosen])+'\n',
        Path(__file__).name:Path(__file__).read_text()},metadata)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('dataset','evidence','output'):p.add_argument('--'+name,required=True)
    print(canonical(run(**vars(p.parse_args()))))

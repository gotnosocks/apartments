"""Freeze the top fifteen distinct-unit absolute residuals with exact own evidence."""
import argparse
import hashlib
import json
from pathlib import Path

from apartments.bayesian_evidence import load_evidence
from apartments.corrections import canonical
from apartments.main_analysis import load_selection, resolve_path
from apartments.research_pipeline import digest, publish_bundle


def run(selection, output):
    chosen, experiment, dataset=load_selection(selection)
    fit=json.loads((experiment/'fit/complete.json').read_text())
    residual_path=experiment/'fit/residuals.jsonl'
    if digest(residual_path)!=fit['files']['residuals.jsonl']:
        raise ValueError('Selected residual artifact differs from fit')
    residuals=[json.loads(s) for s in residual_path.read_text().split('\n') if s]
    selected=[];seen=set()
    for residual in sorted(residuals,key=lambda r:(-abs(r['residual_log']),r['audit_id'])):
        if residual['unit_id'] in seen:continue
        seen.add(residual['unit_id']);selected.append(residual)
        if len(selected)==15:break
    evidence=resolve_path(chosen['evidence'])
    captures=load_evidence(dataset,evidence)
    rows={r['audit_id']:r for r in (json.loads(s) for s in (dataset/'observations.jsonl').read_text().split('\n') if s)}
    cases=[]
    for rank,residual in enumerate(selected,1):
        row=rows[residual['audit_id']]
        if any(row[k]!=residual[k] for k in ('unit_id','source_listing_id','building','asking_rent','period')):
            raise ValueError('Residual and source identities differ')
        cases.append({'rank':rank,'residual':residual,'source_row':row,
            'source_row_sha256':hashlib.sha256(canonical(row).encode()).hexdigest(),
            'captures':captures[row['audit_id']]})
    if load_selection(selection)[0]!=chosen:raise ValueError('Selection changed during review preparation')
    return publish_bundle(output,{'cases.jsonl':''.join(canonical(c)+'\n' for c in cases),
        Path(__file__).name:Path(__file__).read_text()},
        {'version':'selected-absolute-residual-research-inputs-v1','selection_sha256':digest(selection),
         'fit_manifest_sha256':chosen['fit_manifest_sha256'],'dataset_manifest_sha256':chosen['source_manifest_sha256'],
         'evidence_manifest_sha256':chosen['evidence_manifest_sha256'],
         'residuals_sha256':fit['files']['residuals.jsonl'],'rows':len(rows),'cases':len(cases),
         'selection_rule':'All fitted observations; decreasing abs(residual_log), audit_id ascending; first distinct unit; top15.'})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selection',type=Path,default=Path('config/main-analysis.json'))
    parser.add_argument('--output',type=Path,required=True)
    print(canonical(run(**vars(parser.parse_args()))))

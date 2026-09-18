"""Explicit selection of a verified PyMC posterior for the main analysis workflow."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .corrections import canonical
from .research_pipeline import digest

VERSION = 'main-pymc-analysis-selection-v1'
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SELECTION = ROOT/'config/main-analysis.json'


def resolve_path(value, root=ROOT):
    if not isinstance(value,str) or not value.strip():
        raise ValueError('A saved Bayesian experiment and dataset are required')
    path=Path(value)
    return path if path.is_absolute() else Path(root)/path


def load_selection(path=DEFAULT_SELECTION, *, root=ROOT):
    selection=json.loads(Path(path).read_text())
    if selection.get('version')!=VERSION or selection.get('model_family')!='pymc_bayesian':
        raise ValueError('The main analysis requires a selected PyMC Bayesian model')
    experiment=resolve_path(selection.get('experiment'),root)
    dataset=resolve_path(selection.get('dataset'),root)
    for field,manifest in [('fit_manifest_sha256',experiment/'fit/complete.json'),
                           ('protocol_manifest_sha256',experiment/'protocol/complete.json'),
                           ('source_manifest_sha256',dataset/'complete.json')]:
        if not manifest.is_file() or manifest.is_symlink() or digest(manifest)!=selection.get(field):
            raise ValueError('Selected main model binding differs: '+field)
    return selection,experiment,dataset


def select(experiment,dataset,output=DEFAULT_SELECTION):
    # Verify the full source/posterior and both convergence gates, without fitting.
    from models import bayesian_feature_report as report
    experiment,dataset=Path(experiment).resolve(),Path(dataset).resolve()
    verified,_=report.build_report(experiment,dataset,top=1)
    def portable(path):
        return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
    result={'version':VERSION,'model_family':'pymc_bayesian',
            'experiment':portable(experiment),'dataset':portable(dataset),
            'fit_manifest_sha256':digest(experiment/'fit/complete.json'),
            'protocol_manifest_sha256':digest(experiment/'protocol/complete.json'),
            'source_manifest_sha256':digest(dataset/'complete.json'),
            'source_observations_sha256':verified['source_observations_sha256'],
            'protocol_sha256':verified['protocol_sha256'],
            'cohort':verified['cohort'],
            'selection_reason':'Main contribution, residual and counterfactual analysis uses the accepted PyMC joint posterior.',
            'uncertainty':'Conditional posterior uncertainty; source errors, omitted features and incomplete market coverage remain separate.'}
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    temporary=output.with_name(output.name+'.tmp')
    temporary.write_text(canonical(result)+'\n');temporary.replace(output)
    load_selection(output)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment',type=Path,required=True)
    parser.add_argument('--dataset',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=DEFAULT_SELECTION)
    args=parser.parse_args()
    print(canonical(select(args.experiment,args.dataset,args.output)))

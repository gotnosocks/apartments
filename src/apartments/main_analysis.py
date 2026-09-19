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
    if 'evidence' in selection or 'evidence_manifest_sha256' in selection:
        evidence = resolve_path(selection.get('evidence'), root)
        manifest = evidence/'complete.json'
        if not manifest.is_file() or manifest.is_symlink() or digest(manifest) != selection.get('evidence_manifest_sha256'):
            raise ValueError('Selected main model binding differs: evidence_manifest_sha256')
    if 'source_review' in selection or 'source_review_manifest_sha256' in selection:
        if not selection.get('evidence'):
            raise ValueError('Selected source review requires its description archive')
        review = resolve_path(selection.get('source_review'), root)
        manifest = review/'complete.json'
        if not manifest.is_file() or manifest.is_symlink() or digest(manifest) != selection.get('source_review_manifest_sha256'):
            raise ValueError('Selected main model binding differs: source_review_manifest_sha256')
    issue_fields = {'source_issues','source_issues_manifest_sha256','source_issue_cases'}
    if issue_fields & selection.keys():
        if not issue_fields <= selection.keys() or not selection.get('evidence'):
            raise ValueError('Selected source issues require complete bindings and their matching description archive')
        count = selection['source_issue_cases']
        if type(count) is not int or count < 0:
            raise ValueError('Selected source issue case count is invalid')
        issues = resolve_path(selection['source_issues'], root)
        manifest = issues/'complete.json'
        if not manifest.is_file() or manifest.is_symlink() or digest(manifest) != selection['source_issues_manifest_sha256']:
            raise ValueError('Selected main model binding differs: source_issues_manifest_sha256')
    return selection,experiment,dataset


def select(experiment,dataset,output=DEFAULT_SELECTION, *, evidence=None, source_review=None, source_issues=None):
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
    if evidence is not None:
        from .bayesian_evidence import load_evidence
        evidence = Path(evidence).resolve()
        load_evidence(dataset, evidence)
        result.update(evidence=portable(evidence), evidence_manifest_sha256=digest(evidence/'complete.json'))
    if source_review is not None:
        if evidence is None:
            raise ValueError('Source review requires the matching description archive')
        from .bayesian_source_review import load_source_review
        source_review = Path(source_review).resolve()
        notes = load_source_review(experiment, dataset, source_review, evidence=evidence)
        result.update(source_review=portable(source_review),
            source_review_manifest_sha256=digest(source_review/'complete.json'),
            source_review_cases=len(notes))
    if source_issues is not None:
        if evidence is None:
            raise ValueError('Source issues require the matching description archive')
        from .source_issues import load_source_issues
        source_issues = Path(source_issues).resolve()
        notes = load_source_issues(dataset, source_issues, evidence=evidence)
        result.update(source_issues=portable(source_issues),
            source_issues_manifest_sha256=digest(source_issues/'complete.json'),
            source_issue_cases=len(notes))
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
    parser.add_argument('--evidence',type=Path,help='Verified description archive for the selected source cohort.')
    parser.add_argument('--source-review',type=Path,help='Source-review notes bound to this fit and description archive.')
    parser.add_argument('--source-issues',type=Path,help='Verified source issue annotations bound to the selected dataset and description archive.')
    args=parser.parse_args()
    print(canonical(select(args.experiment,args.dataset,args.output,evidence=args.evidence,source_review=args.source_review,source_issues=args.source_issues)))

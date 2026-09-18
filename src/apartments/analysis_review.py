"""Read-only, source-bound inspection of a fitted analysis and its contrasts.

The portable runtime remains authoritative for encoding and arithmetic. This
layer supplies observed support, holds unsupported contrasts out of the UI, and
binds the residual index to the exact training dataset and model.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path

from . import pricing, robust_pricing
from .research_pipeline import _verified_bundle


NUMERIC_FIELDS = {
    'bedrooms':('Bedrooms',0.,5.,1.),
    'bathrooms':('Bathrooms',1.,5.,.5),
    'square_feet':('Interior square feet',150.,6000.,25.),
    'listed_floor':('Advertised floor',-5.,150.,1.),
    'physical_floor':('Floors above ground',-5.,150.,1.),
}
CATEGORY_LABELS = {'laundry_type':'Laundry', 'doorman_type':'Doorman',
                   'hvac_type':'HVAC', 'pet_rules':'Pet rules'}


def bundle_signature(*directories):
    """Cache invalidation hint only; load still verifies each artifact's hashes.

    Include every file declared by each completion manifest, so an edited body
    does not reuse an earlier verification merely because the manifest is old.
    """
    stamps=[]
    for directory in directories:
        root=Path(directory).resolve()
        manifest=root/'complete.json'
        meta=json.loads(manifest.read_text())
        for name in ['complete.json',*sorted(meta['files'])]:
            path=(root/name).resolve()
            if not path.is_relative_to(root):
                raise ValueError('Bundle file escapes its directory')
            stat=path.stat()
            stamps.append((str(path),stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns))
    return hashlib.sha256(json.dumps(stamps).encode()).hexdigest()


def _records(data):
    # Unicode line separators can occur inside source descriptions.
    return [json.loads(line) for line in data.decode().split('\n') if line]


def _family(term):
    if term.startswith(('building:','unit:','trend:','season:')):
        return term.split(':',1)[0]
    if term in ('center','intercept'):
        return 'reference'
    if term=='size_missing' or term.endswith(('.unknown','=__unknown__')):
        return 'missingness'
    if term=='log_size_within_bedrooms':
        return 'size'
    if term.startswith('amenity:'):
        return term.split(':',1)[1].split('=',1)[0].split('.',1)[0]
    return 'layout'


class AnalysisWorkspace:
    @classmethod
    def load(cls, model_dir, dataset_dir, residual_dir, evidence_dir=None):
        model=robust_pricing.RobustPricingModel.load(model_dir)
        dm,df=_verified_bundle(dataset_dir,retain={'observations.jsonl'})
        rm,rf=_verified_bundle(residual_dir,retain={'residuals.jsonl','summary.json'})
        if dm.get('dataset_version')!='historical-plus-current-capture-analysis-v1' or dm!=model.artifact['training']['source_manifest']:
            raise ValueError('Analysis requires the exact fitted dataset')
        if (rm.get('version')!='fitted-residual-review-v1' or rm['model_manifest']!=model.manifest
                or rm['dataset_manifest']!=dm or rm['runtime_sha256']!=model.manifest['runtime_sha256']
                or rm['pricing_features_sha256']!=model.manifest['pricing_features_sha256']):
            raise ValueError('Residual bundle does not bind this model and dataset')
        workspace=cls(model,_records(df['observations.jsonl']),_records(rf['residuals.jsonl']),
                      json.loads(rf['summary.json']),{'model':model.manifest,'dataset':dm,'residuals':rm})
        if evidence_dir is not None:workspace.attach_evidence(evidence_dir)
        return workspace

    def __init__(self,model,rows,residuals,summary,manifests):
        self.model,self.rows,self.residuals,self.summary,self.manifests=model,rows,residuals,summary,manifests
        self._rows={r['audit_id']:r for r in rows}
        self._residuals={r['audit_id']:r for r in residuals}
        if len(self._rows)!=len(rows) or len(self._residuals)!=len(residuals) or set(self._rows)!=set(self._residuals):
            raise ValueError('Residual and source membership mismatch or duplicate identity')
        for key,row in self._rows.items():
            residual=self._residuals[key]
            if any(row.get(f)!=residual.get(f) for f in ('unit_id','building_id','period','source_listing_id','asking_rent')):
                raise ValueError('Residual target or identity differs from the source row')
            for f in ('asking_rent','fitted_rent','asking_minus_fitted','asking_vs_fitted_percent','log_residual','absolute_log_residual'):
                if not math.isfinite(float(residual[f])):
                    raise ValueError('Nonfinite residual index')
            if residual['asking_rent']<=0 or residual['fitted_rent']<=0:
                raise ValueError('Nonpositive residual rent')
            ratio=residual['asking_rent']/residual['fitted_rent']
            expected={'asking_minus_fitted':residual['asking_rent']-residual['fitted_rent'],
                      'asking_vs_fitted_percent':100*(ratio-1), 'log_residual':math.log(ratio),
                      'absolute_log_residual':abs(math.log(ratio))}
            if any(not math.isclose(residual[f],v,rel_tol=1e-9,abs_tol=1e-8) for f,v in expected.items()):
                raise ValueError('Residual arithmetic mismatch')
        self.fields={name:{'label':label,'kind':'numeric','minimum':low,'maximum':high,'step':step}
                     for name,(label,low,high,step) in NUMERIC_FIELDS.items()}
        self.fields.update({name:{'label':label,'kind':'category',
            'options':[v for v in model.encoder['amenity_categories'][name] if v!='__unknown__']}
            for name,label in CATEGORY_LABELS.items()})
        self.fields['elevator']={'label':'Elevator','kind':'boolean','options':[False,True]}
        self._normalized={key:robust_pricing._normalize(row) for key,row in self._rows.items()}
        self._support={};self._histories=defaultdict(list);self._captures=defaultdict(list)
        for residual in residuals:
            self._histories[residual['unit_id']].append(residual)
        for history in self._histories.values():
            history.sort(key=lambda r:(r['period'],r['audit_id']))
        self._layouts=Counter((float(r['bedrooms']),float(r['bathrooms'])) for r in rows)
        for field in self.fields:
            known=[];by_building=defaultdict(set);by_unit=defaultdict(set)
            for key,row in self._normalized.items():
                value=self._value(field,row)
                if value is None:continue
                known.append((value,row['building_id'],row['unit_id']))
                by_building[row['building_id']].add(value);by_unit[row['unit_id']].add(value)
            self._support[field]={'known':known,'counts':Counter(v for v,_,_ in known),
                                  'by_building':by_building,'by_unit':by_unit}

    def attach_evidence(self,evidence_dir):
        """Attach verified original text, never the experiment's inferred values."""
        manifest,files=_verified_bundle(evidence_dir,retain={'evidence.jsonl'})
        if manifest.get('version') not in ('cohort-outdoor-evidence-v1','fitted-description-archive-v1') or manifest['dataset_manifest']!=self.manifests['dataset']:
            raise ValueError('Archived descriptions do not bind the fitted dataset')
        captures=defaultdict(list);seen=set()
        for capture in _records(files['evidence.jsonl']):
            key=capture['audit_id'];row=self._rows.get(key)
            if row is None:raise ValueError('Archived description has no fitted observation')
            allowed=set(row.get('capture_ids') or [])|{row.get('capture_id')}
            if (capture['source_listing_id']!=str(row['source_listing_id']) or capture['unit_id']!=row['unit_id']
                    or capture['capture_id'] not in allowed or (key,capture['capture_id']) in seen):
                raise ValueError('Archived description identity or capture membership mismatch')
            if pricing._timestamp(capture['source_collected_at'])>pricing._timestamp(row['known_at']):
                raise ValueError('Archived description is later than the observation knowledge clock')
            if capture.get('description_interpreted_at') and pricing._timestamp(capture['description_interpreted_at'])>pricing._timestamp(row['known_at']):
                raise ValueError('Recovered description is later than the observation knowledge clock')
            seen.add((key,capture['capture_id']))
            text=capture.get('description');source_path='/description'
            details=capture.get('property_details')
            if isinstance(details,dict) and isinstance(details.get('description'),str):
                text=details['description'];source_path='/propertyDetails/description'
            if capture.get('description_sha256') is not None and (
                    not isinstance(text,str) or hashlib.sha256(text.encode()).hexdigest()!=capture['description_sha256']):
                raise ValueError('Archived description text hash mismatch')
            captures[key].append({**{f:capture.get(f) for f in ('capture_id','source_collected_at','description_interpreted_at',
                'body_sha256','raw_listing_sha256','known_at','source_listing_id')},'description':text,'source_path':source_path})
        for values in captures.values():values.sort(key=lambda c:(c['source_collected_at'],str(c['capture_id'])))
        self._captures=captures;self.manifests={**self.manifests,'descriptions':manifest}

    def _value(self,field,row):
        if field in CATEGORY_LABELS:
            v=pricing._category(row.get(field));return None if v=='__unknown__' else v
        if field=='elevator':
            return pricing._boolean(row.get(field))
        v=pricing._number(row.get(field))
        if field=='square_feet' and v is not None and not 150<=v<=6000:return None
        return v

    def factor_support(self):
        result=[]
        for field,s in self._support.items():
            counts=s['counts'];known=len(s['known'])
            result.append({'field':field,'label':self.fields[field]['label'],'known_rows':known,
                'unknown_rows':len(self.rows)-known,'known_values':len(counts),
                'buildings_with_known_variation':sum(len(v)>1 for v in s['by_building'].values()),
                'units_with_known_variation':sum(len(v)>1 for v in s['by_unit'].values()),
                'minimum':min(counts) if counts and field not in CATEGORY_LABELS else None,
                'maximum':max(counts) if counts and field not in CATEGORY_LABELS else None})
        # These encoded families are not editable when their physical contrast
        # lacks support; showing their counts makes that limitation inspectable.
        for field,s in self.model.encoder['amenity_numeric'].items():
            if field in self.fields:continue
            result.append({'field':field,'label':field,'known_rows':s['known'],'unknown_rows':s['unknown'],
                'known_values':s['unique_values'],'buildings_with_known_variation':None,
                'units_with_known_variation':None,'minimum':None,'maximum':None})
        return result

    def detail(self,audit_id):
        row=self._rows[audit_id];residual=self._residuals[audit_id]
        prediction=self.model.predict(row,row['period'])
        if not math.isclose(prediction['predicted_rent'],residual['fitted_rent'],rel_tol=1e-10,abs_tol=1e-7):
            raise ValueError('Selected residual does not reproduce the fitted model')
        groups=defaultdict(list)
        for term,value in prediction['log_components'].items():groups[_family(term)].append(value)
        return {'source_record':row,'feature_values':{f:self._value(f,self._normalized[audit_id]) for f in self.fields},
            'source_captures':self._captures.get(audit_id,[]),
            'residual':residual,'log_components':prediction['log_components'],
            'log_contributions_by_family':{k:math.fsum(v) for k,v in sorted(groups.items())},
            'unit_history':self._histories[row['unit_id']], 'warnings':prediction['warnings'],
            'provenance':{'analysis_knowledge_cutoff':self.model.artifact['training']['knowledge_cutoff'],
                'observation_month':row['period'],'price_basis':row.get('analysis_price_basis'),
                'capture_ids':row.get('capture_ids') or [row.get('capture_id')],
                'source_collected_at':row.get('collected_at'),'attribute_assumption':row.get('attribute_assumption'),
                'time_basis':row.get('time_basis'),'known_at':row.get('known_at'),
                'all_rows_in_fit':True,'availability':'Saved capture state; current availability is not verified.',
                'model_membership_sha256':self.model.artifact['training']['membership_sha256']}}

    def contrast(self,audit_id,changes):
        if not isinstance(changes,dict) or not changes or set(changes)-set(self.fields):
            raise ValueError('Choose one or more supported editable attributes')
        changes=dict(changes)
        for field,value in changes.items():
            spec=self.fields[field]
            if value is None:continue
            if spec['kind']=='numeric':
                number=pricing._number(value)
                if number is None or not spec['minimum']<=number<=spec['maximum']:
                    raise ValueError(field+': value outside allowed range')
                if field in ('bedrooms','bathrooms') and (number*(2 if field=='bathrooms' else 1))%1:
                    raise ValueError(field+': unsupported layout increment')
                changes[field]=number
            elif spec['kind']=='boolean' and not isinstance(value,bool):
                raise ValueError('Elevator must be true, false or unknown')
            elif spec['kind']=='category' and value not in spec['options']:
                raise ValueError(field+': category not present in the fitted encoding')
        row=self._normalized[audit_id];changed={**row,**changes}
        changes={f:v for f,v in changes.items() if self._value(f,row)!=self._value(f,changed)}
        if not changes:
            raise ValueError('Choose an attribute value different from the observation')
        # None may otherwise be filled back from a source alias during runtime
        # normalization. Remove only aliases of intentionally changed fields.
        clean={k:v for k,v in row.items() if k not in {a for f in changes for a in pricing.ALIASES.get(f,())}}
        if any(changes.get(f,'unchanged') is None for f in ('bedrooms','bathrooms')):
            raise ValueError('Bedrooms and bathrooms require known values')
        estimate=self.model.marginal_contributions(clean,changes,row['period'])
        support=[];warnings=list(estimate['warnings']);unsupported=False;unknown=False
        for field in changes:
            before,after=self._value(field,row),self._value(field,changed)
            s=self._support[field];values=s['counts'];local=s['by_building'].get(row['building_id'],set())
            variation=sum(len(v)>1 for v in s['by_building'].values())
            support.append({'field':field,'reference':before,'destination':after,
                'known_rows':len(s['known']),'unknown_rows':len(self.rows)-len(s['known']),
                'reference_rows':values.get(before,0),'destination_rows':values.get(after,0),
                'reference_units':len({u for v,_,u in s['known'] if v==before}),
                'destination_units':len({u for v,_,u in s['known'] if v==after}),
                'destination_buildings':len({b for v,b,_ in s['known'] if v==after}),
                'observed_minimum':min(values) if values and field not in CATEGORY_LABELS else None,
                'observed_maximum':max(values) if values and field not in CATEGORY_LABELS else None,
                'building_known_values':len(local),'buildings_with_known_variation':variation,
                'units_with_known_variation':sum(len(v)>1 for v in s['by_unit'].values())})
            if before is None or after is None:unknown=True
            if len(values)<2:
                unsupported=True;warnings.append(field+': fewer than two observed known values; a magnitude contrast is not identified.')
            if not variation:
                warnings.append(field+': no within-building known-value variation; decomposition depends on group shrinkage.')
            if len(local)<2:
                warnings.append(field+': this building has no observed known-value contrast; the estimate borrows the cohort association.')
            if field in CATEGORY_LABELS or field in ('bedrooms','bathrooms','elevator'):
                if after is not None and not values.get(after):
                    unsupported=True;warnings.append(field+': destination value has no observed training support.')
                elif after is not None and values.get(after,0)<25:
                    warnings.append(field+': destination has fewer than 25 training rows; counts are not independent apartments.')
            elif after is not None and values and not min(values)<=after<=max(values):
                unsupported=True;warnings.append(field+': destination is outside the observed numeric range.')
        layout=(float(changed['bedrooms']),float(changed['bathrooms']))
        if not self._layouts[layout]:
            unsupported=True;warnings.append('The changed bedroom/bathroom combination has no training observations.')
        if unknown:
            warnings.append('Unknown-to-known changes mix reporting patterns with attribute values; no physical amenity value is displayed.')
        if 'bedrooms' in changes:
            warnings.append('Changing bedrooms also recomputes bedroom-specific area normalization; stated area and group effects remain fixed.')
        warnings.append('Observed support does not establish independent identification, causal value or physical feasibility.')
        return {'status':'unsupported' if unsupported else 'reporting_comparison' if unknown else 'supported_association',
                'show_estimate':not unsupported and not unknown,'estimate':estimate,'support':support,
                'warnings':sorted(set(warnings)),
                'held_fixed':['Canonical apartment and building, including their fitted effects',
                              'Observation month, trend and seasonality',
                              'All attributes not explicitly changed; interactions are recomputed']}

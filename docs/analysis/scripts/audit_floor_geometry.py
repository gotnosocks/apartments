"""Read-only source-bound audit of fixed features and completed posterior geometry."""
import argparse
import json
from pathlib import Path
import numpy as np,pandas as pd,xarray as xr
from models.bayesian_floor_increment_design import FeatureDesign
from models.bayesian_feature_experiment_v4 import load_data
from apartments.research_pipeline import digest, publish_bundle
from apartments.corrections import canonical

def main(args):
    root=Path(args.experiment)
    d,src=load_data(Path(args.dataset)); design=FeatureDesign.load(root/'fit'); X=design.matrix(d); names=design.features
    bindings={str(p):digest(p) for p in [root/'fit/complete.json',root/'fit/posterior.nc',root/'fit/feature-design.json',root/'fit/parameter-diagnostics.csv',Path(args.dataset)/'complete.json',Path(args.reference)/'fit/complete.json',Path(args.reference)/'fit/posterior.nc']}
    for base in [root,Path(args.reference)]:
     manifest=json.loads((base/'fit/complete.json').read_text())
     if bindings[str(base/'fit/posterior.nc')]!=manifest['files']['posterior.nc']:raise ValueError('Posterior differs from completed fit')
    out={}
    std=X.std(0); corr=np.corrcoef(X.T);pairs=[]
    for i in range(len(names)):
     for j in range(i):
      if abs(corr[i,j])>.97:pairs.append([names[j],names[i],float(corr[i,j])])
    s=np.linalg.svd(X/std,compute_uv=False);out['design']={'shape':list(X.shape),'rank':int(np.linalg.matrix_rank(X)),'singular_min':float(s[-1]),'singular_max':float(s[0]),'correlations_over_097':sorted(pairs,key=lambda a:-abs(a[2]))}
    out['unit_counts']=d.groupby('unit_id').size().describe().to_dict();out['single_observation_units']=int((d.groupby('unit_id').size()==1).sum())
    for group in ['unit_id','building']:
     centered=pd.DataFrame(X).groupby(d[group].to_numpy()).transform('mean').to_numpy(); within=X-centered
     ratios=(within**2).sum(0)/(X**2).sum(0)
     out['within_'+group+'_variance_fraction']={n:float(v) for n,v in zip(names,ratios)}
    with xr.open_dataset(root/'fit/posterior.nc',group='posterior',engine='h5netcdf') as p:
     beta=p.beta.values.reshape(-1,len(names)); bc=np.corrcoef(beta.T); pairs=[]
     for i in range(len(names)):
      for j in range(i):
       if abs(bc[i,j])>.7:pairs.append([names[j],names[i],float(bc[i,j])])
     out['posterior_beta_correlations_over_07']=sorted(pairs,key=lambda a:-abs(a[2]))
     out['scales']={n:np.quantile(p[n].values,[.025,.5,.975]).tolist() for n in ['sigma','sigma_unit','sigma_building','trend_scale','season_scale']}
     floors=[i for i,n in enumerate(names) if n.startswith('listed_floor_gt_')]; high=beta[:,floors].sum(1)
     b=p.building_effect; building_names=b.building.values.tolist()
     # All building effect correlations with full floor-range contrast, read moderate blocks.
     matches=[]
     for start in range(0,len(building_names),64):
      vals=b.isel(building=slice(start,start+64)).values.reshape(-1,min(64,len(building_names)-start)); c=np.corrcoef(np.column_stack([high,vals]).T)[0,1:]
      matches.extend([[str(building_names[start+j]),float(v)] for j,v in enumerate(c)])
     out['floor_range_building_correlations']=sorted(matches,key=lambda a:-abs(a[1]))[:15]
    with xr.open_dataset(root/'fit/posterior.nc',group='sample_stats',engine='h5netcdf') as p:
     out['sampler']={n:{'quantiles':np.quantile(p[n].values,[0,.5,.9,.99,1]).tolist(),'chain_medians':np.median(p[n].values,axis=1).tolist()} for n in ['n_steps','depth','step_size','mean_tree_accept']}
    q=pd.read_csv(root/'fit/parameter-diagnostics.csv');out['lowest_ess']=q.nsmallest(20,'ess_bulk').to_dict('records')
    out['trajectory_cost']={}
    for base in [Path(args.reference),root]:
     with xr.open_dataset(base/'fit/posterior.nc',group='sample_stats',engine='h5netcdf') as stats:
      steps=stats.n_steps.values.flatten(); tail=np.sort(steps)[-max(1,int(np.ceil(.01*len(steps)))):]
      out['trajectory_cost'][base.name]={'mean_steps':float(steps.mean()),'median_steps':float(np.median(steps)),
       'q99_steps':float(np.quantile(steps,.99)),'largest_one_percent_step_share':float(tail.sum()/steps.sum()),
       'over1023_fraction':float((steps>1023).mean()),'over1023_step_share':float(steps[steps>1023].sum()/steps.sum()),'total_steps':int(steps.sum())}
    if any(digest(Path(p))!=h for p,h in bindings.items()):raise ValueError('Input changed during audit')
    out['bindings']=bindings
    out['interpretation']=['Observational geometry audit, not a causal attribution of runtime to individual parameters.',
     'Within-group variance fractions include changes in measurement availability; they do not establish physical apartment changes.',
     'Full feature rank excludes group indicators and does not establish likelihood identification against free unit effects.',
     'Step counts measure trajectory work, not matched end-to-end wall time.']
    publish_bundle(Path(args.output),{'audit.json':canonical(out)+'\n','audit_floor_geometry.py':Path(__file__).read_text()},
     {'version':'floor-posterior-geometry-audit-v1','bindings':bindings})
    print(canonical({'output':args.output,'rank':out['design']['rank'],'trajectory_cost':out['trajectory_cost']}))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ['experiment','dataset','reference','output']:parser.add_argument('--'+key,required=True)
    main(parser.parse_args())

import json
from pathlib import Path
import numpy as np
import pandas as pd
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle,digest,publish_bundle
from models import bayesian_floor_elevator_design as module

root=Path('data/model/chelsea-reviewed-elevator-analysis-20260919')
manifest,files=_verified_bundle(root,retain={'observations.jsonl'})
data=pd.DataFrame([json.loads(line) for line in files['observations.jsonl'].decode().split('\n') if line])
data.period=pd.to_datetime(data.period);data.square_feet=pd.to_numeric(data.square_feet,errors='coerce')
result=[]
for mode in module.MODES:
 d=module.FeatureDesign(data,mode=mode)
 matrix=d.matrix(data)
 base=matrix[:,:len(d.base.features)]
 contrasts=[]
 for low,high in [(2,3),(3,4),(4,5),(2,5)]:
  y=module.floor_contrast_vector(d,data,low,high,True)
  n=module.floor_contrast_vector(d,data,low,high,False)
  contrasts.append({'lower':low,'upper':high,'no_elevator_log_prior_sd':float(np.linalg.norm(n*d.prior_scales)),
   'elevator_log_prior_sd':float(np.linalg.norm(y*d.prior_scales)),
   'interaction_difference_log_prior_sd':float(np.linalg.norm((y-n)*d.prior_scales))})
 result.append({'mode':mode,'features':d.features,'columns':len(d.features),
  'base_rank':int(np.linalg.matrix_rank(base)),'full_rank':int(np.linalg.matrix_rank(matrix)),
  'endpoint_support':d.endpoint_support,'contrasts':contrasts,
  'base_columns_bitwise_unchanged':bool(np.array_equal(base,d.base.matrix(data)))})
 print(canonical(result[-1]),flush=True)
output=Path('data/model/chelsea-lower-floor-elevator-design-audit-20260919')
publish_bundle(output,{'design-audit.json':canonical({'version':module.VERSION,'rows':len(data),'candidates':result,
 'status':'unfitted_candidate_designs','limitations':'Matrix rank is not hierarchical identification or evidence for an effect. Unknown access uses the midpoint interaction convention. Upper interactions saturate above floor 5. Priors differ from the no-interaction base.'})+'\n',
 Path(module.__file__).name:Path(module.__file__).read_text(),Path(__file__).name:Path(__file__).read_text()},
 {'version':module.VERSION,'source_manifest_sha256':digest(root/'complete.json'),
  'source_observations_sha256':manifest['files']['observations.jsonl']})

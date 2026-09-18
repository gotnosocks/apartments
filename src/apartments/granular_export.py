"""Streaming, non-aggregating interpretations of immutable archive snapshots."""
from __future__ import annotations
import gzip
import hashlib
import json
import re
from pathlib import Path
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

from .unit_canonical import ASSOCIATION_RULE

import pyarrow as pa
import pyarrow.parquet as pq

VERSION = 'granular-v1'
LISTING_FILTER = 'rental-canonical-unit-v1'
PAGE_CLASSIFICATION = 'media-gallery-v1'
# Numeric clocks are UTC Unix seconds. Original date strings stay in source JSON.
FIELDS = {
 'snapshots': 'snapshot_id:i generation:i url:s body_hash:s kind:s page_type:s observed_at:f extraction_version:i',
 'fetch_observations': 'observation_id:i generation:i url:s fetched_at:f status:i content_type:s headers:s body_hash:s not_modified:i error:s',
 'listing_observations': 'snapshot_id:i url:s listing_id:s listing_type:s building_slug:s unit_label:s bedrooms:f bathrooms:f square_feet:f room_count:f collected_at:f parsed_at:f source_created_at:s source_updated_at:s features_json:s amenities_json:s pricing_json:s raw_listing_json:s canonical_href:s canonical_unit_url:s canonical_unit_error:s parse_status:s error:s',
 'listing_exclusions': 'snapshot_id:i url:s listing_id:s listing_type:s collected_at:f reason:s canonical_href:s canonical_unit_error:s parse_status:s error:s',
 'media_gallery_observations': 'snapshot_id:i url:s page_type:s listing_id:s listing_type:s building_id:s collected_at:f parsed_at:f canonical_href:s canonical_unit_url:s canonical_unit_error:s property_details_json:s media_json:s signature_media_gallery_json:s raw_gallery_json:s parse_status:s error:s',
 'event_mentions': 'snapshot_id:i episode_index:i event_index:i listing_id:s event_listing_id:s event_category:s event_date:s price:f status:s percent_change:f event_json:s event_key:s',
 'building_observations': 'snapshot_id:i building_slug:s building_id:s residential_units:f latitude:f longitude:f raw_building_json:s parse_status:s error:s',
 'inventory_rows': 'snapshot_id:i row_index:i listing_url:s row_kind:s row_html:s record_json:s',
 'inventory_observations': 'snapshot_id:i count:i expected_counts_json:s row_count:i raw_inventory_json:s parse_status:s error:s',
 'source_changes': 'snapshot_id:i source_path:s change_index:i source_timestamp:s price:f source_json:s',
 'frontier': 'generation:i url:s kind:s state:s attempts:i',
 'url_aliases': 'generation:i url:s target_url:s reason:s created:f',
}
SCHEMAS = {name: pa.schema([(x.split(':')[0], {'i':pa.int64(),'f':pa.float64(),'s':pa.string()}[x.split(':')[1]]) for x in fields.split()]) for name,fields in FIELDS.items()}

def implementation_hash():
 h=hashlib.sha256()
 for name in ('granular_export.py','granular_parse.py','granular_media.py','unit_canonical.py','canonical_units.py'):
  h.update((Path(__file__).parent/name).read_bytes())
 return h.hexdigest()

def dumps(value):
 return json.dumps(value, ensure_ascii=False, separators=(',', ':'), default=str)

def write_json(path, value):
 path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
 tmp=path.with_suffix('.tmp'); tmp.write_text(dumps(value)); tmp.replace(path)

class Tables:
 def __init__(self, root, part, names):
  self.root=Path(root);self.part=part;self.names=names;self.buffers={n:[] for n in names};self.writers={};self.counts={n:0 for n in names}
 def add(self,name,row):
  self.buffers[name].append(row);self.counts[name]+=1
  if len(self.buffers[name])>=256:self.flush(name)
 def flush(self,name):
  path=self.root/name/f'{self.part}.parquet';path.parent.mkdir(parents=True,exist_ok=True)
  if name not in self.writers:self.writers[name]=pq.ParquetWriter(path,SCHEMAS[name],compression='zstd')
  if self.buffers[name]:
   self.writers[name].write_table(pa.Table.from_pylist(self.buffers[name],schema=SCHEMAS[name]));self.buffers[name].clear()
 def close(self):
  for n in self.names:self.flush(n);self.writers[n].close()

def connect(snapshot):
 c=sqlite3.connect(Path(snapshot).resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
 c.row_factory=sqlite3.Row;c.execute('PRAGMA cache_size=-16384');return c

def prepare(snapshot,root,ledger,chunk_size=2000):
 from .granular_media import page_type
 root=Path(root);root.mkdir(parents=True,exist_ok=True)
 from apartments.corrections import Overlay
 overlay=Overlay(ledger)
 config={'version':VERSION,'unit_association_rule':ASSOCIATION_RULE,'listing_filter':LISTING_FILTER,'page_classification':PAGE_CLASSIFICATION,'snapshot':str(snapshot),'snapshot_bytes':Path(snapshot).stat().st_size,'chunk_size':chunk_size,'corrections':overlay.manifest}
 # The raw export freezes corrections but deliberately does not guess an attribute
 # effective date. A corrected projection can apply this ledger at model time.
 ledger_bytes=Path(ledger).read_bytes();config['ledger_sha256']=hashlib.sha256(ledger_bytes).hexdigest()
 plan_path=root/'plan.json'
 if plan_path.exists():
  previous=json.loads(plan_path.read_text())
  for key in ('version','listing_filter','page_classification','unit_association_rule','snapshot','snapshot_bytes','chunk_size','ledger_sha256'):
   if previous.get(key)!=config[key]:raise ValueError(f'Run identity changed: {key}; choose a new output ID')
  return previous
 (root/'corrections.jsonl').write_bytes(ledger_bytes)
 c=connect(snapshot);tables=Tables(root,'metadata',['snapshots','fetch_observations','frontier','url_aliases']);jobs=[];batch=[]
 for r in c.execute('SELECT p.id snapshot_id,p.generation,p.url,p.body_hash,p.observed observed_at,p.extraction_version,f.kind FROM snapshots p JOIN scope_urls s USING(generation,url) LEFT JOIN frontier f USING(generation,url) ORDER BY p.id'):
  row=dict(r);row['page_type']=page_type(row);tables.add('snapshots',row);batch.append(row)
  if len(batch)>=chunk_size:jobs.append(batch);batch=[]
 if batch:jobs.append(batch)
 print('Snapshot metadata',tables.counts, 'shards',len(jobs),flush=True)
 for r in c.execute('SELECT o.id observation_id,o.generation,o.url,o.fetched fetched_at,o.status,o.content_type,o.headers,o.body_hash,o.not_modified,o.error FROM observations o JOIN scope_urls s USING(generation,url) ORDER BY o.id'):tables.add('fetch_observations',dict(r))
 for r in c.execute('SELECT f.generation,f.url,f.kind,f.state,f.attempts FROM frontier f JOIN scope_urls s USING(generation,url)'):tables.add('frontier',dict(r))
 for r in c.execute('SELECT a.* FROM url_aliases a JOIN scope_urls s USING(generation,url)'):tables.add('url_aliases',dict(r))
 c.close();tables.close()
 for i,job in enumerate(jobs):write_json(root/'jobs'/f'{i:05d}.json',job)
 config.update(created_at=time.time(),shards=len(jobs),metadata_counts=tables.counts)
 write_json(plan_path,config);return config

def shard_files_valid(root, previous):
 for name,count in previous['counts'].items():
  path=Path(root)/name/f"part-{previous['part']:05d}.parquet"
  try:
   if pq.read_metadata(path).num_rows!=count:return False
  except (OSError,pa.ArrowInvalid):return False
 return True

def read_bodies(job,body_root):
 from .granular_media import page_type
 # Bound cold-volume read latency without creating thousands of queued futures
 # or keeping an entire shard of decompressed documents in memory.
 def read(item):
  if page_type(item) not in {'listing','media_gallery'}:return item,None
  try:
   h=item['body_hash']
   return item,gzip.decompress((Path(body_root)/h[:2]/f'{h}.gz').read_bytes())
  except Exception as e:return item,e
 with ThreadPoolExecutor(max_workers=8) as pool:
  for start in range(0,len(job),32):
   yield from pool.map(read,job[start:start+32])

def process_shard(snapshot,root,part,body_root):
 from apartments.granular_parse import parse_listing
 from apartments.granular_media import page_type, parse_media_gallery
 from apartments.unit_canonical import canonical_fields
 from streeteasy_archive.scope import objects
 root=Path(root);marker=root/'checkpoints'/f'{part:05d}.json'
 if marker.exists():
  previous=json.loads(marker.read_text())
  if previous.get('implementation_sha256')!=implementation_hash():raise ValueError('Parser changed; choose a new run ID')
  if shard_files_valid(root,previous):return previous
  marker.unlink()
 job=json.loads((root/'jobs'/f'{part:05d}.json').read_text());c=connect(snapshot)
 tables=Tables(root,f'part-{part:05d}',['listing_observations','listing_exclusions','media_gallery_observations','event_mentions','building_observations','inventory_rows','inventory_observations','source_changes'])
 errors=[];started=time.time()
 for n,(item,body) in enumerate(read_bodies(job,body_root)):
  sid=item['snapshot_id'];url=item['url'];kind=page_type(item)
  if kind=='media_gallery':
   try:
    if isinstance(body,Exception):raise body
    if body is None:raise ValueError('Missing gallery body')
    row=parse_media_gallery(body,url)
   except Exception as e:
    row={'page_type':'media_gallery','parse_status':'error','error':f'{type(e).__name__}: {e}'}
   row.update(snapshot_id=sid,url=url,collected_at=item['observed_at'],parsed_at=time.time())
   tables.add('media_gallery_observations',row)
   if row.get('parse_status')!='ok':errors.append({'snapshot_id':sid,'url':url,'page_type':kind,'error':row.get('error')})
  elif kind=='listing':
   try:
    if isinstance(body,Exception):raise body
    if body is None:raise ValueError('Missing listing body')
    row,events=parse_listing(body,url)
   except Exception as e:
    row={**(canonical_fields(body,url) if isinstance(body,bytes) else {}),
      'parse_status':'error','error':f'{type(e).__name__}: {e}',
      'listing_type':'sale' if re.search(r'/(?:sale|sales)/',url) else 'rental'};events=[]
   row.update(snapshot_id=sid,url=url,collected_at=item['observed_at'],parsed_at=time.time())
   if row.get('listing_type')=='rental' and not row.get('canonical_unit_url'):
    tables.add('listing_exclusions',{**row,'reason':'rental_missing_canonical_unit_page',
      'canonical_unit_error':row.get('canonical_unit_error') or 'Canonical unit page could not be read'})
   else:
    tables.add('listing_observations',row)
    for ev in events:tables.add('event_mentions',dict(ev,snapshot_id=sid))
    source=json.loads(row['raw_listing_json']) if row.get('raw_listing_json') else {}
    for path,changes in (('pricing.priceChanges',(source.get('pricing') or {}).get('priceChanges')),('statusChanges',source.get('statusChanges'))):
     if not isinstance(changes,list):continue
     for j,change in enumerate(changes):
      obj=change if isinstance(change,dict) else {}
      price=obj.get('price');price=float(price) if isinstance(price,(int,float)) and not isinstance(price,bool) else None
      tables.add('source_changes',{'snapshot_id':sid,'source_path':path,'change_index':j,'source_timestamp':obj.get('changedAt'),'price':price,'source_json':dumps(change)})
   if row.get('parse_status')!='ok':errors.append({'snapshot_id':sid,'url':url,'error':row.get('error')})
  elif kind in ('building','inventory'):
   try:
    raw=c.execute('SELECT extracted FROM snapshots WHERE id=?',(sid,)).fetchone()[0];data=json.loads(raw)
    if kind=='inventory':
     inv=data.get('inventory') or {};rows=inv.get('rows') or [];records=inv.get('records') or []
     for j in range(max(len(rows),len(records))):
      rec=records[j] if j<len(records) else {}
      tables.add('inventory_rows',{'snapshot_id':sid,'row_index':j,'listing_url':rec.get('url'),'row_kind':rec.get('kind'),'row_html':rows[j] if j<len(rows) else None,'record_json':dumps(rec)})
     tables.add('inventory_observations',{'snapshot_id':sid,'count':inv.get('count'),'row_count':max(len(rows),len(records)),'expected_counts_json':dumps(inv.get('expected_counts')),'raw_inventory_json':dumps(inv),'parse_status':'ok' if inv else 'missing','error':None if inv else 'No saved inventory'})
    else:
     slug=urlsplit(url).path.split('/')[2]
     primary=next((o for o in objects(data) if o.get('slug')==slug and 'residentialUnitCount' in o),None)
     tables.add('building_observations',{'snapshot_id':sid,'building_slug':slug,'building_id':str(primary['id']) if primary and primary.get('id') is not None else None,'residential_units':primary.get('residentialUnitCount') if primary else None,'latitude':primary.get('latitude') if primary else None,'longitude':primary.get('longitude') if primary else None,'raw_building_json':dumps(primary),'parse_status':'ok' if primary else 'missing','error':None if primary else 'No primary building object'})
   except Exception as e:
    errors.append({'snapshot_id':sid,'url':url,'error':str(e)})
    table='building_observations' if kind=='building' else 'inventory_observations'
    tables.add(table,{'snapshot_id':sid,'parse_status':'error','error':f'{type(e).__name__}: {e}'})
  if n and n%250==0:print(f'Shard {part}: {n}/{len(job)} ({time.time()-started:.0f}s)',flush=True)
 c.close();tables.close()
 result={'part':part,'version':VERSION,'implementation_sha256':implementation_hash(),'snapshots':len(job),'counts':tables.counts,'seconds':time.time()-started,'errors':errors}
 write_json(marker,result);return result


def finish(root):
 """Validate and finalize a local or cloud transform, including unit grouping."""
 from apartments.granular_export import write_json, implementation_hash, shard_files_valid, SCHEMAS
 from apartments.granular_quality import audit_dataset
 from apartments.canonical_units import build_canonical_units, SCHEMAS as UNIT_SCHEMAS
 root=Path(root)
 if (root/'complete.json').exists():raise ValueError('Dataset is complete; choose a new output ID')
 plan=json.loads((root/'plan.json').read_text())
 import pyarrow.parquet as pq
 for table,count in plan['metadata_counts'].items():
  if pq.read_metadata(root/table/'metadata.parquet').num_rows!=count:raise ValueError(f'Metadata count mismatch: {table}')
 checkpoints=[json.loads((root/'checkpoints'/f'{i:05d}.json').read_text()) for i in range(plan['shards'])]
 if any(c.get('implementation_sha256')!=implementation_hash() for c in checkpoints):raise ValueError('Mixed parser versions; choose a new run ID')
 if not all(shard_files_valid(root,c) for c in checkpoints):raise ValueError('Missing or damaged shard output; resume before finalizing')
 from apartments.inventory_links import build_inventory_links, SCHEMA as LINK_SCHEMA
 import apartments.inventory_links as links_module
 import hashlib
 links_marker=root/'inventory-links.json'
 if links_marker.exists():
  links=json.loads(links_marker.read_text())
  if links['implementation_sha256']!=hashlib.sha256(Path(links_module.__file__).read_bytes()).hexdigest():raise ValueError('Inventory link parser changed; choose a new derived interpretation')
  if pq.read_metadata(root/'inventory_row_links'/'derived.parquet').num_rows!=links['rows']:raise ValueError('Inventory link output changed')
 else:
  links=build_inventory_links(root);write_json(links_marker,links)
 units=build_canonical_units(root)
 audit=audit_dataset(root)
 audit['canonical_unit_association']=units
 audit['inventory_link_interpretation']=links
 audit['implementation_sha256']=implementation_hash()
 audit['provenance']=plan;audit['finished_at']=time.time()
 audit['export_errors']={'count':sum(len(c['errors']) for c in checkpoints),'examples':[e for c in checkpoints for e in c['errors']][:30]}
 from apartments.granular_report import render_report
 if any(c['expected_unobserved'] for c in audit.get('coverage',{}).values()):raise ValueError('Snapshot coverage reconciliation failed')
 if any(audit['referential_checks'].values()):raise ValueError('Broken snapshot links')
 occurrences=audit['event_mentions']['occurrence_uniqueness']
 if occurrences['rows']!=occurrences['distinct_occurrences']:raise ValueError('Duplicate occurrence primary keys')
 schemas={**SCHEMAS,'inventory_row_links':LINK_SCHEMA,**UNIT_SCHEMAS}
 link_audit=audit['inventory_row_links']
 if link_audit['missing_source_rows'] or link_audit['unlinked_source_rows'] or link_audit['rows']!=link_audit['distinct_occurrences']:raise ValueError('Inventory link reconciliation failed')
 write_json(root/'schemas.json',{name:{f.name:str(f.type) for f in schema} for name,schema in schemas.items()})
 write_json(root/'quality-report.json',audit)
 (root/'quality-report.md').write_text(render_report(audit))
 write_json(root/'complete.json',{'finished_at':time.time(),'version':plan['version'],'shards':len(checkpoints),'counts':audit['tables']['counts'],'quality_report':'quality-report.json','unit_association_rule':ASSOCIATION_RULE})
 return audit


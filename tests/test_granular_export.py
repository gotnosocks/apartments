import gzip
import json
import sqlite3
from pathlib import Path
import pyarrow.parquet as pq
from apartments.granular_export import prepare, process_shard


def test_preserves_fetches_snapshots_and_repeated_events(tmp_path):
 db=tmp_path/'archive.sqlite3';c=sqlite3.connect(db)
 c.executescript('''CREATE TABLE snapshots(id INTEGER,generation INTEGER,url TEXT,body_hash TEXT,observed REAL,extraction_version INTEGER,extracted TEXT);
 CREATE TABLE scope_urls(generation INTEGER,url TEXT);
 CREATE TABLE frontier(generation INTEGER,url TEXT,kind TEXT,state TEXT,attempts INTEGER);
 CREATE TABLE observations(id INTEGER,generation INTEGER,url TEXT,fetched REAL,status INTEGER,content_type TEXT,headers TEXT,body_hash TEXT,not_modified INTEGER,error TEXT);
 CREATE TABLE url_aliases(generation INTEGER,url TEXT,target_url TEXT,reason TEXT,created REAL);''')
 url='https://streeteasy.com/rental/123'
 c.execute('INSERT INTO scope_urls VALUES(1,?)',(url,));c.execute("INSERT INTO frontier VALUES(1,?,'listing','done',1)",(url,))
 listing={'id':123,'propertyDetails':{'address':{'displayUnit':'04C'},'bedroomCount':1},'propertyHistory':[{'listingId':123,'rentalEventsOfInterest':[{'date':'2020-01-01','price':3000},{'date':'2020-01-01','price':3000}]}]}
 listing['pricing']={'priceChanges':[{'changedAt':'2020-01-01T12:34:56Z','price':3000}]}
 listing['statusChanges']=[{'changedAt':'2020-01-02T01:00:00Z','status':'RENTED'}]
 body=('<html><head><link rel="canonical" href="https://streeteasy.com/building/demo/04c"></head><body><script type="application/json">'+json.dumps({'listing':listing})+'</script>').encode()
 for i,h in enumerate(['aa111','bb222'],1):
  dest=tmp_path/'bodies'/h[:2];dest.mkdir(parents=True);(dest/f'{h}.gz').write_bytes(gzip.compress(body))
  c.execute('INSERT INTO snapshots VALUES(?,1,?,?,?,5,?)',(i,url,h,1000+i,'{}'))
 for i,(status,h) in enumerate([(200,'aa111'),(304,'aa111'),(200,'bb222'),(403,None)],1):
  c.execute('INSERT INTO observations VALUES(?,1,?,?,?, ?,?,?,?,?)',(i,url,1000+i,status,'text/html','{}',h,status==304,'blocked' if status==403 else None))
 c.commit();c.close();ledger=tmp_path/'edits.jsonl';ledger.write_text('');root=tmp_path/'out'
 plan=prepare(db,root,ledger,chunk_size=1)
 assert plan['metadata_counts']['fetch_observations']==4
 for part in range(plan['shards']):
  first=process_shard(db,root,part,tmp_path/'bodies')
  assert process_shard(db,root,part,tmp_path/'bodies')==first
 observations=pq.read_table(root/'listing_observations').to_pylist()
 assert len(observations)==2
 assert all(r['canonical_unit_url']=='https://streeteasy.com/building/demo/04c' for r in observations)
 assert all(r['canonical_href']=='https://streeteasy.com/building/demo/04c' and r['canonical_unit_error'] is None for r in observations)
 from apartments.review_service import ReviewService
 from apartments.unit_source import SourceEvidence
 (root/'complete.json').write_text('{}')
 service=ReviewService(root,tmp_path/'review-state')
 evidence=SourceEvidence(service)
 assert len(evidence.pages)==2 and evidence.error is None
 assert evidence.pages[1]['canonical_url']=='https://streeteasy.com/building/demo/04c'
 assert not (service.state/'unit-source-pages.parquet').exists()
 service.close()
 events=pq.read_table(root/'event_mentions').to_pylist()
 assert len(events)==4
 changes=pq.read_table(root/'source_changes').to_pylist()
 assert len(changes)==4
 assert {r['source_path'] for r in changes}=={'pricing.priceChanges','statusChanges'}
 assert all(r['source_timestamp'] for r in changes)
 assert {r['event_index'] for r in events}=={0,1}
 assert {r['snapshot_id'] for r in events}=={1,2}
 assert len(set(r['event_key'] for r in events))==1
 assert prepare(db,root,ledger,chunk_size=1)==plan

 # A checkpoint alone cannot conceal a missing Parquet part.
 (root/'event_mentions'/'part-00000.parquet').unlink()
 process_shard(db,root,0,tmp_path/'bodies')
 assert pq.read_table(root/'event_mentions').num_rows==4

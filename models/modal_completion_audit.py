"""Read-only completion audit of scoped buildings, inventories and their detail edges."""
import json
from collections import Counter
from pathlib import Path
import sqlite3
import time
from urllib.parse import urljoin
import uuid
import modal

ROOT=Path(__file__).resolve().parents[1]
app=modal.App('chelsea-completion-audit')
volume=modal.Volume.from_name('chelsea-archive')
locks=modal.Dict.from_name('chelsea-scrape-locks')
image=(modal.Image.debian_slim(python_version='3.12').pip_install('parsel==1.10.0')
       .env({'PYTHONPATH':'/root/src'})
       .add_local_dir(ROOT/'src/streeteasy_archive','/root/src/streeteasy_archive',ignore=['__pycache__'])
       .add_local_file(Path(__file__),'/root/modal_completion_audit.py'))

@app.function(image=image,cpu=(2,2),memory=(4096,4096),timeout=3600,
              volumes={'/archive':volume},retries=0,include_source=False)
def audit():
    from streeteasy_archive.scope import summary_counts
    from streeteasy_archive.extract import canonical_url, is_gallery_url
    owner=str(uuid.uuid4())
    if not locks.put('writer',{'owner':owner,'action':'read-only-completion-audit','started_at_epoch':time.time()},skip_if_exists=True):
        raise RuntimeError('Archive writer active')
    db=None
    try:
        volume.reload()
        db=sqlite3.connect('file:/archive/crawls/chelsea-resume/archive.sqlite3?mode=ro',uri=True)
        g=db.execute('SELECT max(id) FROM generations').fetchone()[0]
        scoped={u:(kind,state) for u,kind,state in db.execute('SELECT f.url,f.kind,f.state FROM frontier f JOIN scope_urls s USING(generation,url) WHERE f.generation=?',(g,))}
        roots={r[0] for r in db.execute('SELECT url FROM scope_buildings WHERE generation=?',(g,))}
        snapshots={u:(h,i) for u,h,i in db.execute('SELECT url,body_hash,max(id) FROM snapshots WHERE generation=? GROUP BY url',(g,))}
        latest={u:(i,status,error,h) for u,i,status,error,h in db.execute('''SELECT o.url,o.id,o.status,o.error,o.body_hash FROM observations o
            JOIN (SELECT url,max(id) id FROM observations WHERE generation=? GROUP BY url) l ON l.id=o.id''',(g,))}
        aliases=dict(db.execute('SELECT url,target_url FROM url_aliases WHERE generation=?',(g,)))
        successes={u for u,o in latest.items() if o[2] is None and o[3] and o[1] is not None and (200<=o[1]<300 or o[1]==304) and u in snapshots}
        def resolve(url,seen=()):
            if url in successes:return 'captured' if not seen else 'captured_via_alias_or_redirect'
            if url in seen or len(seen)>=8:return 'resolution_cycle_or_limit'
            if url in aliases:return resolve(aliases[url],(*seen,url))
            observation=latest.get(url)
            if observation and observation[1] in (301,302,303,307,308):
                headers=json.loads(db.execute('SELECT headers FROM observations WHERE id=?',(observation[0],)).fetchone()[0])
                location=next((v for k,v in headers.items() if k.lower()=='location'),None)
                if isinstance(location,str):
                    target=canonical_url(urljoin(url,location))
                    if target:return resolve(target,(*seen,url))
            if observation:return 'HTTP_'+str(observation[1]) if observation[1] else 'error_no_status'
            return scoped.get(url,('', 'not_queued'))[1]
        building_missing=[]; inventory_missing=[]; incomplete=[]; invs=[]; all_links=set(); expected_totals=Counter()
        expected_counts={}; missing_body=[]; cross_capture=[]
        def data(url):
            return json.loads(db.execute('SELECT extracted FROM snapshots WHERE id=?',(snapshots[url][1],)).fetchone()[0])
        for n,url in enumerate(sorted(roots)):
            if url not in successes:building_missing.append({'url':url,'state':resolve(url)});continue
            d=data(url)
            for cat,key in [('rentals','rentalSummary'),('sales','saleSummary')]:
                totals=summary_counts(d,key)
                expected_counts[(url,cat)]=max(totals) if totals else None
                if totals:expected_totals[cat]+=max(totals)
                view=url+'?archive_view=unavailable-'+cat
                if (not totals or max(totals)>0) and view not in successes:
                    inventory_missing.append({'url':view,'expected':max(totals) if totals else None,'state':resolve(view)})
            if n%200==0:print('Building summaries checked',n,flush=True)
        for n,(url,(kind,state)) in enumerate(sorted(scoped.items())):
            if kind!='inventory':continue
            if url not in successes:
                incomplete.append({'url':url,'state':resolve(url)});continue
            d=data(url);inv=d.get('inventory') or {};records=inv.get('records') or inv.get('links') or []
            links={x['url'] for x in inv.get('links',[]) if isinstance(x,dict) and x.get('url')}
            all_links.update(links)
            count=inv.get('count');expected=max(inv.get('expected_counts') or [0])
            category='rentals' if 'unavailable-rentals' in url else 'sales'
            base=url.split('?')[0];building_expected=expected_counts.get((base,category)) or 0
            good=isinstance(count,int) and len(records)==count and count>=expected
            states=Counter(resolve(u) for u in links)
            row={'url':url,'category':category,'complete':good,'rows':len(records),'displayed':count,'expected':expected,'detail_links':len(links),'detail_states':dict(states),'closing_records':sum(x.get('kind')=='closing' for x in records if isinstance(x,dict))}
            invs.append(row)
            if building_expected>len(records):
                dates={u:db.execute('SELECT fetched FROM observations WHERE id=?',(latest[u][0],)).fetchone()[0] for u in (base,url) if u in latest}
                cross_capture.append({**row,'building_summary_expected':building_expected,'capture_times':dates})
            if not good:incomplete.append(row)
            h=snapshots[url][0]
            if not (Path('/archive/bodies')/h[:2]/(h+'.gz')).is_file():missing_body.append(url)
        detail_states=Counter(resolve(u) for u in all_links)
        unresolved=[{'url':u,'state':resolve(u)} for u in sorted(all_links) if not resolve(u).startswith('captured')]
        listing_states=Counter(resolve(u) for u,(kind,state) in scoped.items() if kind=='listing' and not is_gallery_url(u))
        current_errors=Counter(o[2] for u,o in latest.items() if u in scoped and o[2] and o[2]!='redirect observed')
        return {'at':time.time(),'generation':g,'scoped_queue':dict(Counter(kind+':'+state for kind,state in scoped.values())),
                'building_roots':len(roots),'missing_buildings':building_missing,'missing_expected_inventories':inventory_missing,
                'expected_summary_totals':dict(expected_totals),'inventory_counts':dict(Counter(x['category'] for x in invs)),
                'inventory_rows':{cat:sum(x['rows'] for x in invs if x['category']==cat) for cat in ('rentals','sales')},
                'inventory_closings':sum(x['closing_records'] for x in invs),'incomplete_inventories':incomplete,
                'cross_capture_count_discrepancies':cross_capture,'missing_inventory_bodies':missing_body,'inventory_detail_states':dict(detail_states),'inventory_detail_total':len(all_links),
                'unresolved_inventory_details':unresolved,'scoped_listing_states':dict(listing_states),'current_error_counts':dict(current_errors),
                'largest_inventories':sorted(invs,key=lambda x:x['rows'],reverse=True)[:15],
                'limitations':['Queue drainage covers discovered Chelsea scope, not an independent census of every physical unit.',
                               '404/410 outcomes and redirect targets remain explicit; a saved price history does not supply missing episode attributes.']}
    finally:
        if db:db.close()
        locks.pop('writer')  # Read-only: no volume mutation needs committing.

@app.local_entrypoint()
def main():
    report=audit.remote()
    Path('/tmp/chelsea-completion-audit-20260912.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k not in ('largest_inventories','unresolved_inventory_details')},indent=2))

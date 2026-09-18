'use strict';
(() => {
const $=id=>document.getElementById(id);
const state={previewSerial:0,offset:0,limit:25,sort:'listing_count',direction:'desc',listSerial:0,detailSerial:0,data:null,busy:false,mergeRequest:null};
const el=(tag,text,cls)=>{const node=document.createElement(tag);if(text!==undefined)node.textContent=text;if(cls)node.className=cls;return node;};
const num=value=>Number(value||0).toLocaleString();
const value=x=>x==null?'Unknown':String(x);
const money=x=>x==null?'Unknown':`$${Number(x).toLocaleString(undefined,{maximumFractionDigits:2})}`;
const date=x=>new Date(x*1000).toLocaleString();
const requestId=()=>Array.from(crypto.getRandomValues(new Uint8Array(16)),x=>x.toString(16).padStart(2,'0')).join('');
function error(e){$('error').textContent=e.message||String(e);$('error').hidden=false;}
async function api(path,payload){
  const response=await fetch(path,payload?{method:'POST',headers:{'Content-Type':'application/json','X-Review-CSRF':document.querySelector('meta[name="csrf-token"]').content},body:JSON.stringify(payload)}:{cache:'no-store'});
  const data=await response.json();if(!response.ok)throw new Error(data.error||'Request failed');return data;
}
function captureLink(sid){const a=el('a',`Capture ${sid}`);a.href=`/?snapshot_id=${sid}`;a.target='_blank';a.rel='noopener';return a;}
function streetEasyUrls(observations){
  const urls=new Set();
  for(const row of observations){try{
    const url=new URL(row.url);
    if(['https:','http:'].includes(url.protocol)&&(url.hostname==='streeteasy.com'||url.hostname.endsWith('.streeteasy.com')))urls.add(url.href);
  }catch{}}
  return [...urls];
}
function openUnopenedListings(urls,opened){
  for(const url of urls){
    if(opened.has(url))continue;
    // A blank same-origin tab gives us a reliable handle when the browser permits it.
    // Detach the opener and suppress the referrer before navigating to StreetEasy.
    const tab=window.open('about:blank','_blank');
    if(!tab)continue;
    try{
      tab.opener=null;
      const policy=tab.document.createElement('meta');policy.name='referrer';policy.content='no-referrer';
      tab.document.head.append(policy);
      tab.location.replace(url);
      opened.add(url);
    }catch{tab.close();}
  }
  return urls.filter(url=>!opened.has(url)).length;
}
function sourceUnitLink(row){
  const evidence=row.identity_evidence||{},node=el('div');
  if(evidence.canonical_url){const link=el('a','Unit page ↗');link.href=evidence.canonical_url;link.target='_blank';link.rel='noopener noreferrer';node.append(link);}
  else node.append(el('span',evidence.error||'No canonical unit page'));
  node.append(el('small',`Latest listing: ${evidence.latest_listing_id||'Unknown'}`));return node;
}
function observationLinks(row){
  const links=el('div',undefined,'capture-links');links.append(captureLink(row.snapshot_id));
  if(row.url){try{
    const url=new URL(row.url);
    if(['https:','http:'].includes(url.protocol)){
      const source=el('a','StreetEasy ↗');source.href=url.href;source.title=row.url;
      source.target='_blank';source.rel='noopener noreferrer';
      source.setAttribute('aria-label',`Open original StreetEasy listing ${row.listing_id}`);
      links.append(source);
    }
  }catch{}}
  return links;
}
function table(headings,rows){const wrap=el('div',undefined,'table-wrap'),t=el('table'),head=el('thead'),tr=el('tr'),body=el('tbody');for(const h of headings)tr.append(el('th',h));head.append(tr);for(const cells of rows){const line=el('tr');for(const content of cells){const td=el('td');if(content instanceof Node)td.append(content);else td.textContent=String(content);line.append(td);}body.append(line);}t.append(head,body);wrap.append(t);return wrap;}
async function load(){
  const serial=++state.listSerial;$('total').textContent='Loading…';
  const data=await api('/api/units/candidates?'+new URLSearchParams({search:$('search').value.trim(),mode:$('mode').value,queue:$('queue').value,offset:state.offset,limit:state.limit,sort:state.sort,direction:state.direction}));
  if(serial!==state.listSerial)return;
  $('queue').disabled=$('mode').value!=='candidates';
  $('show-supported').textContent=`${num(data.counts.supported)} ready for bulk association`;
  $('show-label-conflicts').textContent=`${num(data.counts.label_conflicts)} shared-latest label conflicts`;
  $('show-label-conflicts').hidden=$('mode').value!=='candidates';
  $('show-review').textContent=`${num(data.counts.review)} need manual review`;
  $('show-supported').hidden=$('show-review').hidden=$('mode').value!=='candidates';
  $('bulk-associations').hidden=$('mode').value!=='candidates'||$('queue').value!=='supported';
  $('preview-associations').disabled=state.busy||!data.counts.supported;
  $('preview-associations').textContent=`Preview all ${num(data.counts.supported)} matching associations`;
  const sorted=data.sort==='listing_count';
  $('listing-count-heading').setAttribute('aria-sort',sorted?(data.direction==='desc'?'descending':'ascending'):'none');
  $('sort-listing-count').textContent='Rental listing IDs '+(sorted?(data.direction==='desc'?'↓':'↑'):'↕');
  $('sort-listing-count').setAttribute('aria-label',`Sort by rental listing ID count, ${sorted&&data.direction==='desc'?'lowest':'highest'} first`);
  state.offset=data.offset;$('total').textContent=`${num(data.total)} ${$('mode').value==='merged'?'saved units':$('mode').value==='separated'?'kept-separate decisions':'unresolved groups'}`;
  $('candidates').replaceChildren();
  for(const item of data.rows){const row=el('tr'),name=el('td'),button=el('button',`${item.building} ${item.unit_label}`,'record-link');button.type='button';button.addEventListener('click',()=>inspect(item.listing_ids).catch(error));name.append(button);if(item.unit_id)name.append(el('small',item.unit_id));const action=el('td'),compare=el('button',item.unit_id?'Open unit':'Compare');compare.addEventListener('click',()=>inspect(item.listing_ids).catch(error));action.append(compare);const evidence=el('td',item.basis==='separate'?'Kept separate':item.unit_id?(item.basis==='streeteasy'?'StreetEasy-associated':'Manually confirmed'):(item.assessment?.eligible?'Ready for bulk association':'Needs manual review'));if(item.assessment?.reasons?.length)evidence.append(el('small',item.assessment.reasons.join('; ')));row.append(name,el('td',num(item.listing_count)),el('td',num(item.capture_count)),evidence,action);$('candidates').append(row);}
  if(!data.rows.length){const row=el('tr'),cell=el('td','No matching records.');cell.colSpan=5;row.append(cell);$('candidates').append(row);}
  $('page').textContent=`${data.total?state.offset+1:0}–${Math.min(state.offset+state.limit,data.total)} of ${num(data.total)}`;
  $('previous').disabled=state.offset===0;$('next').disabled=state.offset+state.limit>=data.total;
  await loadBatches();
}
async function inspect(ids,unitId){
  if(state.busy)return;
  const serial=++state.detailSerial;$('error').hidden=true;
  const params=new URLSearchParams(unitId?{unit_id:unitId}:{listing_ids:ids.join(',')});
  const data=await api('/api/units/inspect?'+params);
  if(serial!==state.detailSerial)return;
  state.data=data;state.mergeRequest=null;render(data);
  history.replaceState(null,'','/units?'+new URLSearchParams(data.unit_id?{unit_id:data.unit_id}:{listing_ids:data.listing_ids.join(',')}));
  $('comparison').scrollIntoView({behavior:'smooth',block:'start'});
}
function mergeConfirmation(unitId,count,basis='manual',separated=false){
  const panel=el('div',undefined,'merge-confirmation');panel.setAttribute('role','status');
  panel.append(el('strong',separated?'✓ Kept separate':basis==='streeteasy'?'✓ StreetEasy association saved':'✓ Merge saved'),el('p',separated?'Saved your decision. These units stay separate and no longer appear as an unresolved merge group.':`${num(count)} rental listing IDs now share one unit identity and one combined history.`));
  const next=el('button','Next manual review group — most listing IDs','primary');next.type='button';
  const hint=el('p','Opens the largest group needing manual review across all buildings.','panel-note');
  next.addEventListener('click',async()=>{
    if(state.busy)return;
    const serial=++state.detailSerial;next.disabled=true;next.textContent='Finding next group…';
    try{
      const matches=await api('/api/units/candidates?'+new URLSearchParams({mode:'candidates',queue:'review',sort:'listing_count',direction:'desc',limit:1,exclude_unit_id:unitId}));
      if(serial!==state.detailSerial)return;
      if(!matches.rows.length){next.textContent='No more manual review groups';hint.textContent='Check Ready for bulk association for routine repeat listings.';return;}
      $('notice').hidden=true;$('search').value='';$('mode').value='candidates';$('queue').value='review';state.offset=0;state.sort='listing_count';state.direction='desc';
      await inspect(matches.rows[0].listing_ids);await load();
    }catch(e){error(e);next.disabled=false;next.textContent='Next manual review group — most listing IDs';}
  });
  panel.append(next,hint);return panel;
}
function render(data){
  const root=$('comparison');root.hidden=false;root.replaceChildren();
  if(data.kept_separate)root.append(mergeConfirmation('',data.listing_ids.length,'manual',true));
  if(data.latest_merge)root.append(mergeConfirmation(data.unit_id,data.listing_ids.length,data.association_basis));
  const first=data.observations[0]?.attributes||{};
  root.append(el('p',data.kept_separate?'Kept separate':data.latest_merge?(data.association_basis==='streeteasy'?'StreetEasy-associated':'Manually confirmed'):data.unit_id?'Single listing identity':'Compare before merging','eyebrow'),el('h2',`${value(first.building_slug)} ${value(first.unit_label)}`),el('p',`${num(data.listing_ids.length)} rental listing IDs · ${num(data.capture_count)} captures · ${num(data.history_events)} distinct reported history events (${num(data.history_mentions)} source mentions)`));
  if(data.unit_id){root.append(el('p',`Unit ID: ${data.unit_id}`,'unit-identity'));const link=el('a','Download unit record and history');link.href='/api/units/export?'+new URLSearchParams({unit_id:data.unit_id});root.append(link);}
  const evidence=data.source_evidence||data.source_assessment;
  if(evidence){
    const section=el('div',undefined,'source-evidence');
    section.append(el('strong',data.kept_separate?'Marked to keep separate':data.source_evidence?'Saved StreetEasy evidence':evidence.eligible?'Ready for bulk association':'Needs manual review'));
    if(evidence.canonical_url){const link=el('a','StreetEasy unit page ↗');link.href=evidence.canonical_url;link.target='_blank';link.rel='noopener noreferrer';section.append(link);}
    section.append(el('p',`Latest listing reference: ${(evidence.latest_listing_ids||[]).join(', ')||'Missing'}.`,'panel-note'));
    if(evidence.eligible)section.append(el('p',evidence.rule==='shared-latest-v2'
      ? 'Every capture shares one latest-listing reference, with matching building/unit labels across that reference. The saved unit ID does not change when StreetEasy’s latest listing changes.'
      : 'The unit page, address labels, latest listing and complete rental-history membership agreed when this association was saved.','panel-note'));
    for(const conflict of evidence.latest_label_conflicts||[])section.append(el('p',`Latest listing ${conflict.latest_listing_id} appears under: ${conflict.labels.map(([b,u])=>`${b||'Unknown building'} ${u||'Unknown unit'}`).join('; ')}.`,'conflict'));
    for(const note of evidence.notes||[])section.append(el('p',note,'panel-note'));
    for(const reason of evidence.reasons||[])section.append(el('p',reason,'panel-note'));
    root.append(section);
  }
  const conflicts=Object.entries(data.attribute_disagreements);
  if(conflicts.length)root.append(el('p','Recorded attributes differ: '+conflicts.map(([field,values])=>`${field.replaceAll('_',' ')}: ${values.join(' / ')}`).join('; ')+'. A shared identity does not assume unchanged condition. Attribute differences belong in the separate attribute review pass.','conflict'));
  const observations=el('section',undefined,'unit-section merge-controls');observations.append(el('h3','Source observations and attributes'));
  const sourceUrls=streetEasyUrls(data.observations);
  const openAll=el('button',`Open all StreetEasy listings (${sourceUrls.length})`);openAll.type='button';openAll.disabled=!sourceUrls.length;
  const tabsNote=el('p',undefined,'panel-note');tabsNote.hidden=true;tabsNote.setAttribute('role','status');
  const openedUrls=new Set();
  openAll.addEventListener('click',()=>{
    const remaining=openUnopenedListings(sourceUrls,openedUrls);
    openAll.textContent=remaining?`Open remaining listings (${remaining})`:'All listings opened';
    openAll.disabled=!remaining;
    tabsNote.textContent=remaining
      ? `${openedUrls.size} of ${sourceUrls.length} listing tabs opened. The browser blocked or could not open the remaining ${remaining}. Allow pop-ups for this review app using the blocked-pop-up icon in the address bar, then click Open remaining listings. You can also click again to open the next permitted tab, or use the individual links below.`
      : `Opened all ${sourceUrls.length} distinct listing URLs.`;
    tabsNote.hidden=false;
  });
  observations.append(openAll,tabsNote);
  observations.append(el('p','Select rental listing IDs to include. Each selection includes all captures shown for that listing.','panel-note'));
  const options=table(['Include rental ID','Source','Source unit reference','Captured','Building / unit','Beds / baths','Square feet','Advertised rent'],[]),body=options.querySelector('tbody');
  for(const listing of data.listings){
    const captures=data.observations.filter(row=>String(row.listing_id)===String(listing.listing_id));
    const label=el('label',undefined,'listing-selection'),box=el('input');box.type='checkbox';box.value=listing.listing_id;box.checked=true;box.setAttribute('aria-label',`Include rental ${listing.listing_id}`);
    const name=el('span',`Rental ${listing.listing_id}`);name.append(el('small',`${listing.capture_count} captures`));if(listing.exclusion)name.append(el('strong',`Excluded: ${listing.exclusion.reason}`));label.append(box,name);
    captures.forEach((row,index)=>{
      const line=el('tr');
      if(index===0){const selection=el('td',undefined,'listing-selection-cell');selection.rowSpan=captures.length;selection.append(label);line.append(selection);}
      for(const content of [observationLinks(row),sourceUnitLink(row),date(row.collected_at),`${value(row.attributes.building_slug)} ${value(row.attributes.unit_label)}`,`${value(row.attributes.bedrooms)} / ${value(row.attributes.bathrooms)}`,value(row.attributes.square_feet),money(row.attributes.asking_price)]){
        const cell=el('td');if(content instanceof Node)cell.append(content);else cell.textContent=String(content);line.append(cell);
      }
      body.append(line);
    });
  }
  observations.append(options);root.append(observations);

  const form=el('form',undefined,'merge-actions'),noteLabel=el('label','Reason (required for merge; optional to keep separate)'),note=el('input');note.required=true;note.placeholder='Why these units should be merged or kept separate';noteLabel.append(note);
  const actions=el('div',undefined,'inline-actions'),recompare=el('button','Compare selected listings'),merge=el('button',data.latest_merge?(data.association_basis==='streeteasy'?'Associated':'Merged'): 'Merge into one unit','primary');recompare.type='button';merge.type='submit';merge.disabled=!!data.unit_id||!!data.separations?.length;const separate=el('button',data.kept_separate?'Kept separate':'Keep separate');separate.type='button';separate.disabled=!!data.unit_id||!!data.kept_separate;actions.append(recompare,merge,separate);form.append(noteLabel,actions);
  const hint=el('p',data.separations?.length?'A saved decision keeps some of these units separate. Undo it before merging across that decision.':data.unit_id?'These listing IDs already resolve to one unit.':'This saves one unit identity for the selected rental IDs and all their captures. Original attributes and review decisions remain attached to their captures.','panel-note');form.append(hint,el('p','Keep separate marks the units in this comparison as not needing a merge. Existing merges within each unit stay in place. Merge any matching listings first.','panel-note'));root.append(form);
  const selected=()=>Array.from(options.querySelectorAll('input:checked'),input=>input.value);
  options.addEventListener('change',()=>{merge.disabled=separate.disabled=true;state.mergeRequest=null;separateRequest=null;hint.textContent='Click Compare selected listings to review the revised selection.';});
  recompare.addEventListener('click',()=>inspect(selected()).catch(error));
  note.addEventListener('input',()=>{state.mergeRequest=null;separateRequest=null;});
  let separateRequest=null;
  separate.addEventListener('click',async()=>{
    if(state.busy||separate.disabled)return;
    let saved;
    try{
      const author=$('author').value.trim(),reason=note.value.trim()||'Reviewed: these units do not need to be merged';
      if(!author)throw new Error('Enter your reviewer name.');
      if(!separateRequest||separateRequest.author!==author)separateRequest={listing_ids:data.listing_ids,author,reason,identity_revision:data.identity_revision,review_revision:data.review_revision,request_id:requestId()};
      state.busy=true;for(const control of root.querySelectorAll('input,button'))control.disabled=true;
      separate.textContent='Saving decision…';saved=await api('/api/units/separate',separateRequest);state.busy=false;
      separate.textContent='Kept separate';root.prepend(mergeConfirmation('',data.listing_ids.length,'manual',true));
      await inspect(data.listing_ids);await load();
    }catch(e){state.busy=false;if(saved){error(new Error(`Keep-separate decision saved, but the page could not refresh: ${e.message}`));}else{for(const control of root.querySelectorAll('input,button'))control.disabled=false;merge.disabled=!!data.unit_id||!!data.separations?.length;separate.textContent='Keep separate';error(e);}}
  });
  for(const decision of data.separations||[]){
    const undo=el('details'),undoForm=el('form',undefined,'merge-actions'),label=el('label','Reason for undoing'),reason=el('input'),button=el('button','Undo keep separate');
    undo.append(el('summary',`Kept separate: ${decision.listing_ids.join(', ')}`),el('p',`${decision.author}: ${decision.reason}`,'panel-note'));
    reason.required=true;label.append(reason);undoForm.append(label,button);undo.append(undoForm);root.append(undo);
    let payload=null;
    reason.addEventListener('input',()=>{payload=null;});
    undoForm.addEventListener('submit',async event=>{
      event.preventDefault();if(state.busy)return;let saved;
      try{
        const author=$('author').value.trim();if(!author)throw new Error('Enter your reviewer name.');
        if(!payload||payload.author!==author)payload={separation_id:decision.id,identity_revision:data.identity_revision,author,reason:reason.value.trim(),request_id:requestId()};
        state.busy=true;button.disabled=true;saved=await api('/api/units/separate/undo',payload);state.busy=false;
        $('notice').textContent='Keep-separate decision undone. These listings can be considered for merging again.';$('notice').hidden=false;
        await inspect(data.listing_ids);await load();
      }catch(e){state.busy=false;button.disabled=!!saved;error(saved?new Error(`Decision undone, but the page could not refresh: ${e.message}`):e);}
    });
  }
  form.addEventListener('submit',async event=>{
    event.preventDefault();if(state.busy||merge.disabled)return;
    let saved;
    try{
      const author=$('author').value.trim(),reason=note.value.trim();if(!author||!reason)throw new Error('Enter your reviewer name and evidence for the merge.');
      if(!state.mergeRequest||state.mergeRequest.author!==author)state.mergeRequest={listing_ids:data.listing_ids,author,reason,identity_revision:data.identity_revision,review_revision:data.review_revision,request_id:requestId()};
      state.busy=true;for(const control of root.querySelectorAll('input,button'))control.disabled=true;
      merge.textContent='Saving merge…';
      saved=await api('/api/units/merge',state.mergeRequest);
      state.busy=false;history.replaceState(null,'','/units?'+new URLSearchParams({unit_id:saved.unit_id}));
      merge.textContent='Merged';root.prepend(mergeConfirmation(saved.unit_id,saved.listing_ids.length));
      root.scrollIntoView({behavior:'smooth',block:'start'});
      await inspect(null,saved.unit_id);await load();
    }catch(e){state.busy=false;if(saved){error(new Error(`Merge saved, but the page could not refresh: ${e.message}`));}else{error(e);for(const control of root.querySelectorAll('input,button'))control.disabled=false;merge.textContent='Merge into one unit';}}
  });
  if(data.latest_merge){
    const undo=el('details'),summary=el('summary','Undo the latest identity merge'),undoForm=el('form',undefined,'merge-actions'),label=el('label','Reason for undoing'),reason=el('input'),button=el('button','Undo merge');reason.required=true;label.append(reason);undoForm.append(label,button);undo.append(summary,el('p',`${data.latest_merge.author}: ${data.latest_merge.reason}`,'panel-note'),undoForm);root.append(undo);
    let undoRequest=null;reason.addEventListener('input',()=>{undoRequest=null;});
    undoForm.addEventListener('submit',async event=>{event.preventDefault();if(state.busy)return;try{if(!undoRequest)undoRequest={merge_id:data.latest_merge.id,identity_revision:data.identity_revision,author:$('author').value.trim(),reason:reason.value.trim(),request_id:requestId()};state.busy=true;button.disabled=true;await api('/api/units/undo',undoRequest);state.busy=false;history.replaceState(null,'','/units');$('notice').textContent='Identity merge undone. Original records and corrections are preserved.';$('notice').hidden=false;await inspect(data.listing_ids);await load();}catch(e){state.busy=false;button.disabled=false;error(e);}});
  }
  const timeline=el('section',undefined,'unit-section');timeline.append(el('h3',data.unit_id?'Unit history':data.separations?.length?'Reported history across these listings':'Combined history after merge'),el('p','Exact repeated event evidence is combined. Different listing episodes, statuses, prices, and corrected versions remain distinct. Event dates below are separate from capture dates above.','panel-note'));
  timeline.append(table(['Event date','History listing ID','Status','Price','Source evidence'],data.history.map(event=>{
    const refs=el('details');refs.append(el('summary',`${event.occurrences.length} mentions`));const links=el('div',undefined,'capture-links');for(const occurrence of event.occurrences){const line=el('div');line.append(captureLink(occurrence.snapshot_id),el('span',` · entry ${occurrence.episode_index}/${occurrence.event_index}`));links.append(line);}refs.append(links);
    const price=el('div',money(event.price));if(event.excluded)price.append(el('strong','Excluded listing'));if(event.price!==event.raw_price)price.append(el('small',`Source: ${money(event.raw_price)}`));if(event.conflicting_version)price.append(el('small','Multiple reported versions'));if(event.overlay_warning)price.append(el('small',event.overlay_warning));return [value(event.event_date),value(event.event_listing_id),value(event.status),price,refs];
  })));root.append(timeline);
}
async function loadBatches(){
  const data=await api('/api/units/batches');
  const root=$('batch-list');root.replaceChildren();
  if(!data.rows.length){root.append(el('p','No association batches saved yet.','panel-note'));return;}
  for(const batch of data.rows){
    const form=el('form',undefined,'merge-actions'),label=el('label','Reason for undoing this batch'),reason=el('input'),button=el('button',`Undo ${num(batch.active_groups)} associations`);
    form.append(el('p',`${batch.recorded_at} · ${batch.author} · ${num(batch.group_count)} groups saved, ${num(batch.active_groups)} associations not undone.`));
    if(!batch.active_groups){root.append(form);continue;}
    reason.required=true;label.append(reason);form.append(label,button);root.append(form);
    let payload=null;
    reason.addEventListener('input',()=>{payload=null;});
    form.addEventListener('submit',async event=>{event.preventDefault();if(state.busy)return;
      try{const author=$('author').value.trim();if(!author)throw new Error('Enter your reviewer name.');
        if(!payload||payload.author!==author)payload={batch_id:batch.batch_id,identity_revision:data.identity_revision,author,reason:reason.value.trim(),request_id:requestId()};
        state.busy=true;button.disabled=true;await api('/api/units/associations/undo',payload);state.busy=false;
        $('notice').textContent='Association batch undone. Original listings, attributes, and history are preserved.';$('notice').hidden=false;
        $('comparison').hidden=true;$('association-preview').hidden=true;await load();
      }catch(e){state.busy=false;button.disabled=false;error(e);}
    });
  }
}
function clearProposal(){if(state.busy)return;state.previewSerial++;$('association-preview').hidden=true;}
$('preview-associations').addEventListener('click',async()=>{
  if(state.busy)return;const serial=++state.previewSerial;$('preview-associations').disabled=true;$('error').hidden=true;
  try{
    const data=await api('/api/units/associations/preview',{search:$('search').value.trim()});
    if(serial!==state.previewSerial)return;
    const root=$('association-preview');root.replaceChildren();root.hidden=false;
    root.append(el('h2',`Associate ${num(data.group_count)} unit groups`),el('p',`${num(data.listing_count)} rental listing IDs · ${num(data.capture_count)} captures. Search: ${data.search||'all buildings'}. This includes every matching ready group, across all pages.`));
    root.append(el('p','Each group will receive its own durable unit ID labeled “StreetEasy-associated.” The ID and saved membership do not depend on which listing StreetEasy calls latest. These are source associations, not manual physical verification. Attributes, prices, and capture dates remain unchanged. You can undo a whole batch or an individual association.'));
    const download=el('a','Download the complete proposal and evidence');download.href='/api/units/proposal?'+new URLSearchParams({token:data.token});root.append(download);
    root.append(el('h3',`First ${data.examples.length} groups`),table(['Building / unit','Listing IDs'],data.examples.map(x=>[`${x.building} ${x.unit_label}`,x.listing_ids.join(', ')])));
    const save=el('button',`Save ${num(data.group_count)} StreetEasy associations`,'primary'),cancel=el('button','Cancel');save.type=cancel.type='button';const actions=el('div',undefined,'inline-actions');actions.append(save,cancel);root.append(actions);
    cancel.addEventListener('click',clearProposal);
    let payload=null;
    save.addEventListener('click',async()=>{if(state.busy)return;let saved;
      try{const author=$('author').value.trim();if(!author)throw new Error('Enter your reviewer name.');
        if(!payload||payload.author!==author)payload={token:data.token,author};
        state.busy=true;save.disabled=cancel.disabled=true;save.textContent='Saving associations…';
        saved=await api('/api/units/associations/apply',payload);state.busy=false;
        root.replaceChildren(el('h2','✓ StreetEasy associations saved'),el('p',`${num(saved.group_count)} groups now have shared unit identities. Undo options are in Saved association batches below.`));
        const next=el('button','Review remaining exceptions','primary');next.type='button';next.addEventListener('click',()=>{$('mode').value='candidates';$('queue').value='review';$('search').value='';state.offset=0;load().catch(error);});root.append(next);
        $('comparison').hidden=true;history.replaceState(null,'','/units');await load();
      }catch(e){state.busy=false;if(saved){error(new Error(`Associations saved, but the page could not refresh: ${e.message}`));}else{save.disabled=cancel.disabled=false;save.textContent=`Save ${num(data.group_count)} StreetEasy associations`;error(e);}}
    });
    root.scrollIntoView({behavior:'smooth',block:'start'});
  }catch(e){error(e);}finally{$('preview-associations').disabled=false;}
});
for(const [id,queue] of [['show-supported','supported'],['show-review','review'],['show-label-conflicts','label_conflicts']])$(id).addEventListener('click',()=>{if(state.busy)return;clearProposal();$('mode').value='candidates';$('queue').value=queue;state.offset=0;load().catch(error);});
$('queue').addEventListener('change',()=>{if(state.busy)return;clearProposal();state.offset=0;load().catch(error);});
$('sort-listing-count').addEventListener('click',()=>{if(state.busy)return;state.direction=state.sort==='listing_count'&&state.direction==='desc'?'asc':'desc';state.sort='listing_count';state.offset=0;load().catch(error);});
$('filters').addEventListener('submit',event=>{event.preventDefault();if(state.busy)return;clearProposal();state.offset=0;load().catch(error);});
$('mode').addEventListener('change',()=>{if(state.busy)return;clearProposal();state.offset=0;load().catch(error);});
$('previous').addEventListener('click',()=>{if(state.busy)return;state.offset=Math.max(0,state.offset-state.limit);load().catch(error);});
$('next').addEventListener('click',()=>{if(state.busy)return;state.offset+=state.limit;load().catch(error);});
$('manual').addEventListener('submit',event=>{event.preventDefault();const ids=$('manual-ids').value.split(/[\s,]+/).filter(Boolean);inspect([...new Set(ids)]).catch(error);});
load().catch(error);
const params=new URLSearchParams(location.search);if(params.has('unit_id'))inspect(null,params.get('unit_id')).catch(error);else if(params.has('listing_ids'))inspect(params.get('listing_ids').split(',')).catch(error);
})();

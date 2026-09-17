'use strict';
(() => {
const $=id=>document.getElementById(id);
const state={offset:0,limit:25,listSerial:0,detailSerial:0,data:null,busy:false,mergeRequest:null};
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
function table(headings,rows){const wrap=el('div',undefined,'table-wrap'),t=el('table'),head=el('thead'),tr=el('tr'),body=el('tbody');for(const h of headings)tr.append(el('th',h));head.append(tr);for(const cells of rows){const line=el('tr');for(const content of cells){const td=el('td');if(content instanceof Node)td.append(content);else td.textContent=String(content);line.append(td);}body.append(line);}t.append(head,body);wrap.append(t);return wrap;}
async function load(){
  const serial=++state.listSerial;$('total').textContent='Loading…';
  const data=await api('/api/units/candidates?'+new URLSearchParams({search:$('search').value.trim(),mode:$('mode').value,offset:state.offset,limit:state.limit}));
  if(serial!==state.listSerial)return;
  state.offset=data.offset;$('total').textContent=`${num(data.total)} ${$('mode').value==='merged'?'merged units':'possible matches'}`;
  $('candidates').replaceChildren();
  for(const item of data.rows){const row=el('tr'),name=el('td'),button=el('button',`${item.building} ${item.unit_label}`,'record-link');button.type='button';button.addEventListener('click',()=>inspect(item.listing_ids).catch(error));name.append(button);if(item.unit_id)name.append(el('small',item.unit_id));const action=el('td'),compare=el('button',item.unit_id?'Open unit':'Compare');compare.addEventListener('click',()=>inspect(item.listing_ids).catch(error));action.append(compare);row.append(name,el('td',num(item.listing_count)),el('td',num(item.capture_count)),action);$('candidates').append(row);}
  if(!data.rows.length){const row=el('tr'),cell=el('td','No matching records.');cell.colSpan=4;row.append(cell);$('candidates').append(row);}
  $('page').textContent=`${data.total?state.offset+1:0}–${Math.min(state.offset+state.limit,data.total)} of ${num(data.total)}`;
  $('previous').disabled=state.offset===0;$('next').disabled=state.offset+state.limit>=data.total;
}
async function inspect(ids,unitId){
  if(state.busy)return;
  const serial=++state.detailSerial;$('error').hidden=true;
  const params=new URLSearchParams(unitId?{unit_id:unitId}:{listing_ids:ids.join(',')});
  const data=await api('/api/units/inspect?'+params);
  if(serial!==state.detailSerial)return;
  state.data=data;state.mergeRequest=null;render(data);
  $('comparison').scrollIntoView({behavior:'smooth',block:'start'});
}
function render(data){
  const root=$('comparison');root.hidden=false;root.replaceChildren();
  const first=data.observations[0]?.attributes||{};
  root.append(el('p',data.latest_merge?'Merged unit':data.unit_id?'Single listing identity':'Compare before merging','eyebrow'),el('h2',`${value(first.building_slug)} ${value(first.unit_label)}`),el('p',`${num(data.listing_ids.length)} rental listing IDs · ${num(data.capture_count)} captures · ${num(data.history_events)} distinct reported history events (${num(data.history_mentions)} source mentions)`));
  if(data.unit_id){root.append(el('p',`Unit ID: ${data.unit_id}`,'unit-identity'));const link=el('a','Download unit record and history');link.href='/api/units/export?'+new URLSearchParams({unit_id:data.unit_id});root.append(link);}
  const conflicts=Object.entries(data.attribute_disagreements);
  if(conflicts.length)root.append(el('p','Recorded attributes differ: '+conflicts.map(([field,values])=>`${field.replaceAll('_',' ')}: ${values.join(' / ')}`).join('; ')+'. Merging identifies the same home; it does not assume its condition stayed unchanged.','conflict'));
  const options=el('div',undefined,'merge-listings merge-controls');
  for(const listing of data.listings){const label=el('label'),box=el('input');box.type='checkbox';box.value=listing.listing_id;box.checked=true;box.setAttribute('aria-label',`Include rental ${listing.listing_id}`);label.append(box,el('span',`Rental ${listing.listing_id}`),el('small',`${listing.capture_count} captures`));options.append(label);}
  root.append(options);
  const form=el('form',undefined,'merge-actions'),noteLabel=el('label','Why do these listings refer to the same unit?'),note=el('input');note.required=true;note.placeholder='Evidence for the shared unit identity';noteLabel.append(note);
  const actions=el('div',undefined,'inline-actions'),recompare=el('button','Compare selected listings'),merge=el('button','Merge into one unit','primary');recompare.type='button';merge.type='submit';merge.disabled=!!data.unit_id;actions.append(recompare,merge);form.append(noteLabel,actions);
  const hint=el('p',data.unit_id?'These listing IDs already resolve to one unit.':'This saves one unit identity for the selected rental IDs and all their captures. Original attributes and review decisions remain attached to their captures.','panel-note');form.append(hint);root.append(form);
  const selected=()=>Array.from(options.querySelectorAll('input:checked'),input=>input.value);
  options.addEventListener('change',()=>{merge.disabled=true;state.mergeRequest=null;hint.textContent='Click Compare selected listings to review the revised selection.';});
  recompare.addEventListener('click',()=>inspect(selected()).catch(error));
  note.addEventListener('input',()=>{state.mergeRequest=null;});
  form.addEventListener('submit',async event=>{
    event.preventDefault();if(state.busy||merge.disabled)return;
    try{
      const author=$('author').value.trim(),reason=note.value.trim();if(!author||!reason)throw new Error('Enter your reviewer name and evidence for the merge.');
      if(!state.mergeRequest||state.mergeRequest.author!==author)state.mergeRequest={listing_ids:data.listing_ids,author,reason,identity_revision:data.identity_revision,review_revision:data.review_revision,request_id:requestId()};
      state.busy=true;for(const control of root.querySelectorAll('input,button'))control.disabled=true;
      const saved=await api('/api/units/merge',state.mergeRequest);
      state.busy=false;history.replaceState(null,'','/units?'+new URLSearchParams({unit_id:saved.unit_id}));
      $('notice').textContent=`Saved one unit identity for ${saved.listing_ids.length} rental listings.`;$('notice').hidden=false;
      await inspect(null,saved.unit_id);await load();
    }catch(e){error(e);state.busy=false;for(const control of root.querySelectorAll('input,button'))control.disabled=false;}
  });
  if(data.latest_merge){
    const undo=el('details'),summary=el('summary','Undo the latest identity merge'),undoForm=el('form',undefined,'merge-actions'),label=el('label','Reason for undoing'),reason=el('input'),button=el('button','Undo merge');reason.required=true;label.append(reason);undoForm.append(label,button);undo.append(summary,el('p',`${data.latest_merge.author}: ${data.latest_merge.reason}`,'panel-note'),undoForm);root.append(undo);
    let undoRequest=null;reason.addEventListener('input',()=>{undoRequest=null;});
    undoForm.addEventListener('submit',async event=>{event.preventDefault();if(state.busy)return;try{if(!undoRequest)undoRequest={merge_id:data.latest_merge.id,identity_revision:data.identity_revision,author:$('author').value.trim(),reason:reason.value.trim(),request_id:requestId()};state.busy=true;button.disabled=true;await api('/api/units/undo',undoRequest);state.busy=false;history.replaceState(null,'','/units');$('notice').textContent='Identity merge undone. Original records and corrections are preserved.';$('notice').hidden=false;await inspect(data.listing_ids);await load();}catch(e){state.busy=false;button.disabled=false;error(e);}});
  }
  const observations=el('section',undefined,'unit-section');observations.append(el('h3','Source observations and attributes'));
  observations.append(table(['Source','Rental ID','Captured','Building / unit','Beds / baths','Square feet','Advertised rent'],data.observations.map(row=>[captureLink(row.snapshot_id),row.listing_id,date(row.collected_at),`${value(row.attributes.building_slug)} ${value(row.attributes.unit_label)}`,`${value(row.attributes.bedrooms)} / ${value(row.attributes.bathrooms)}`,value(row.attributes.square_feet),money(row.attributes.asking_price)])));root.append(observations);
  const timeline=el('section',undefined,'unit-section');timeline.append(el('h3',data.unit_id?'Unit history':'Combined history after merge'),el('p','Exact repeated event evidence is combined. Different listing episodes, statuses, prices, and corrected versions remain distinct. Event dates below are separate from capture dates above.','panel-note'));
  timeline.append(table(['Event date','History listing ID','Status','Price','Source evidence'],data.history.map(event=>{
    const refs=el('details');refs.append(el('summary',`${event.occurrences.length} mentions`));const links=el('div',undefined,'capture-links');for(const occurrence of event.occurrences){const line=el('div');line.append(captureLink(occurrence.snapshot_id),el('span',` · entry ${occurrence.episode_index}/${occurrence.event_index}`));links.append(line);}refs.append(links);
    const price=el('div',money(event.price));if(event.price!==event.raw_price)price.append(el('small',`Source: ${money(event.raw_price)}`));if(event.conflicting_version)price.append(el('small','Multiple reported versions'));if(event.overlay_warning)price.append(el('small',event.overlay_warning));return [value(event.event_date),value(event.event_listing_id),value(event.status),price,refs];
  })));root.append(timeline);
}
$('filters').addEventListener('submit',event=>{event.preventDefault();state.offset=0;load().catch(error);});
$('mode').addEventListener('change',()=>{state.offset=0;load().catch(error);});
$('previous').addEventListener('click',()=>{state.offset=Math.max(0,state.offset-state.limit);load().catch(error);});
$('next').addEventListener('click',()=>{state.offset+=state.limit;load().catch(error);});
$('manual').addEventListener('submit',event=>{event.preventDefault();const ids=$('manual-ids').value.split(/[\s,]+/).filter(Boolean);inspect([...new Set(ids)]).catch(error);});
load().catch(error);
const params=new URLSearchParams(location.search);if(params.has('unit_id'))inspect(null,params.get('unit_id')).catch(error);else if(params.has('listing_ids'))inspect(params.get('listing_ids').split(',')).catch(error);
})();

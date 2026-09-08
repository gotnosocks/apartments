'use strict';
const $ = id => document.getElementById(id);
const labels = {listing:'Listing detail',building:'Building',search:'Search page',directory:'Directory',sitemap:'Sitemap',homepage:'Homepage'};
let currentPage=1, selectedUrl=null, detail=null, observation=null, extracted=null, activeTab='overview', requestSerial=0;
const number = value => Number(value||0).toLocaleString();
const date = value => value ? new Date(value*1000).toLocaleString(undefined,{month:'short',day:'numeric',year:'numeric',hour:'2-digit',minute:'2-digit'}) : 'Not fetched';
const bytes = value => value>=1048576 ? (value/1048576).toFixed(1)+' MB' : Math.round(value/1024)+' KB';
function node(tag,text,className){const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(className)el.className=className;return el;}
function params(extra={}){return new URLSearchParams({generation:$('generation').value,...extra}).toString();}
async function get(path){const response=await fetch(path,{cache:'no-store'});const result=await response.json();if(!response.ok)throw new Error(result.error||'Unable to read archive');return result;}
function fail(error){$('error').textContent=error.message;$('error').hidden=false;}
function pageName(url){try{const path=new URL(url).pathname;if(path==='/')return 'StreetEasy homepage';return decodeURIComponent(path).replace(/^\/(building|buildings|for-rent|for-sale|rental|sale)\//,'').replaceAll('-',' ').replaceAll('_',' ');}catch{return url;}}
async function summary(){
 const data=await get('/api/summary?'+params());
 const selected=$('generation').value;
 $('generation').replaceChildren(node('option','Latest'));
 $('generation').firstChild.value='';
 for(const gen of data.generations){const option=node('option',`#${gen.id} · ${gen.name}`);option.value=gen.id;$('generation').append(option);}
 $('generation').value=selected;
 $('details-count').textContent=number(data.captured.listing);
 $('buildings-count').textContent=number(data.captured.building);
 $('responses-count').textContent=number(data.responses);
 $('body-size').textContent=`${number(data.unique_bodies)} unique bodies · ${bytes(data.body_bytes)}`;
 $('pending-count').textContent=number((data.queue.pending||0)+(data.queue.inflight||0));
 $('connection').textContent=data.writer_running?'Archive writer active':'Live archive · idle';
 $('connection').classList.toggle('live',true);
 const gen=data.generation;
 $('crawl-state').textContent=!gen?'No crawl yet':gen.status==='paused'?'Paused · cooldown saved':gen.status==='complete'?'Discovered queue complete':data.writer_running?'Crawl in progress':'Ready to resume';
 const notice=$('coverage-note');notice.hidden=false;
 if(gen?.cooldown && gen.cooldown>Date.now()/1000)notice.textContent=`Crawl paused until ${date(gen.cooldown)}. Queued pages are preserved.`;
 else if(!data.captured.listing)notice.textContent='No listing detail pages have been captured yet. Search pages and queued listing URLs are shown separately; queued URLs are not downloaded data.';
 else notice.textContent='Counts reflect captured pages, not proof of complete historical coverage. Inspect queued pages and crawl issues for gaps.';
 if(data.profile?.neighborhood==='chelsea')notice.textContent += ` Scope: Chelsea + West Chelsea, excluding Hudson Yards. ${number(data.scope_queue?.pending)} scoped pages queued; average delay ${data.profile.delay}s. Directory coverage is not yet verified.`;
 $('archive-path').textContent=data.archive_path;
 $('updated-at').textContent='Updated '+new Date().toLocaleTimeString();
 $('recent-errors').hidden=!data.errors.length;$('errors-list').replaceChildren();
 for(const error of data.errors){const item=node('div',undefined,'issue');item.append(node('strong',error.error),node('div',error.url),node('span',date(error.fetched),'date'));$('errors-list').append(item);}
}
async function pages(){
 const serial=++requestSerial;
 const data=await get('/api/pages?'+params({q:$('query').value,kind:$('kind').value,state:$('state').value,page:currentPage}));
 if(serial!==requestSerial)return;
 $('rows').replaceChildren();$('empty').hidden=!!data.items.length;
 $('result-count').textContent=number(data.total)+' matching pages';
 for(const item of data.items){
  const tr=node('tr');tr.classList.toggle('selected',item.url===selectedUrl);
  const first=node('td');const button=node('button',pageName(item.url),'page-button');button.title=item.url;button.addEventListener('click',()=>selectPage(item.url));
  first.append(button,node('span',new URL(item.url).pathname,'page-path'));
  const type=node('td',labels[item.kind]||item.kind);
  const status=node('td');const captured=item.body_hash&&!item.error&&(item.status>=200&&item.status<300||item.status===304);
  status.append(node('span',item.error?`HTTP ${item.status||'error'}`:captured?item.status===304?'Unchanged':'Captured':item.state==='pending'?'Queued':item.state,`badge ${item.error?'bad':captured?'ok':''}`));
  if(item.fetched)status.append(node('span',date(item.fetched),'date'));
  tr.append(first,type,status);$('rows').append(tr);
 }
 const count=Math.max(1,Math.ceil(data.total/data.page_size));
 $('page-label').textContent=`Page ${data.page} of ${count}`;$('previous').disabled=currentPage<=1;$('next').disabled=currentPage>=count;
}
async function refresh(){try{$('error').hidden=true;await Promise.all([summary(),pages()]);}catch(error){fail(error);}}
function field(label,value){const wrapper=node('div',undefined,'field');wrapper.append(node('dt',label),node('dd',value==null?'—':String(value)));return wrapper;}
async function selectPage(url){
 selectedUrl=url;detail=null;activeTab='overview';extracted=null;observation=null;
 $('inspector-empty').hidden=true;$('inspector-content').hidden=false;$('panel').replaceChildren(node('p','Loading page…','panel-note'));
 $('detail-title').textContent=pageName(url);$('detail-kind').textContent='Page';$('detail-status').replaceChildren();
 $('original-link').href=url;
 try{const result=await get('/api/page?'+params({url}));if(selectedUrl!==url)return;detail=result;observation=detail.history[0]||null;
  $('detail-kind').textContent=labels[detail.page.kind]||detail.page.kind;
  await renderPanel();pages();
 }catch(error){fail(error);}
}
async function loadExtraction(){
 if(!observation?.body_hash)return null;
 if(extracted)return extracted;
 const id=observation.id;const result=await get(`/api/observations/${id}/extraction`);
 if(observation?.id!==id)return null;
 extracted=result;return result;
}
async function renderPanel(){
 if(!detail)return;
 document.querySelectorAll('[data-tab]').forEach(button=>{const selected=button.dataset.tab===activeTab;button.setAttribute('aria-selected',selected);button.tabIndex=selected?0:-1;});
 const panel=$('panel');panel.replaceChildren();
 $('detail-status').replaceChildren(node('span',observation?`HTTP ${observation.status||'error'}`:'Not fetched','badge'),node('span',observation?date(observation.fetched):'Waiting in the crawl queue'));
 if(activeTab==='history'){
  panel.append(node('p',`${number(detail.observation_count)} observations. Showing the latest ${detail.history.length}.`,'panel-note'));
  for(const item of detail.history){const button=node('button',`${date(item.fetched)} · HTTP ${item.status||'error'}`,'history-item');button.append(node('span',`Crawl #${item.generation} · ${item.error|| (item.not_modified?'Unchanged body':'Saved response')}`));button.addEventListener('click',()=>{observation=item;extracted=null;activeTab='overview';renderPanel().catch(fail);});panel.append(button);}
  return;
 }
 if(activeTab==='overview'){
  const dl=node('dl');dl.append(field('URL',detail.page.url),field('Queue state',detail.page.state),field('Request attempts',detail.page.attempts),field('Sitemap last modified',detail.page.lastmod));
  if(observation){dl.append(field('Observation',`#${observation.id} · Crawl #${observation.generation}`),field('Content type',observation.content_type),field('Body SHA-256',observation.body_hash));if(observation.error)dl.append(field('Crawl issue',observation.error));
   const headers=node('details');headers.append(node('summary','Response headers'),node('pre',JSON.stringify(observation.headers,null,2)));dl.append(headers);
  }else panel.append(node('p','This URL is queued. No source or listing details have been downloaded.','panel-note'));
  panel.append(dl);
  const chosen=selectedUrl;const id=observation?.id;const data=await loadExtraction();
  if(data && selectedUrl===chosen && observation?.id===id && activeTab==='overview'){
   if(data.title)$('detail-title').textContent=data.title;
   const description=data.meta?.find(item=>item.name==='description')?.content;
   if(description)dl.prepend(field('Page description',description));
   dl.append(field('Saved structures',`${data.scripts?.length||0} scripts · ${data.tables?.length||0} tables · ${data.links?.length||0} discovered links`));
  }
  return;
 }
 if(!observation?.body_hash){panel.append(node('p','No response body has been captured for this page.','panel-note'));return;}
 const id=observation.id;const tab=activeTab;
 panel.append(node('p','Loading saved response…','panel-note'));
 if(tab==='data'){
  const data=await loadExtraction();if(observation?.id!==id||activeTab!==tab)return;
  panel.replaceChildren(node('p','Derived from the saved response. Raw source remains available for future extraction.','panel-note'),node('pre',JSON.stringify(data,null,2)));
 }else if(tab==='raw'){
  const data=await get(`/api/observations/${id}/raw`);if(observation?.id!==id||activeTab!==tab)return;
  const link=node('a','Download complete response body','source-link');link.href=`/api/observations/${id}/raw?download=1`;
  panel.replaceChildren(link,node('p',data.truncated?'Preview limited to 200 KB. Download contains the complete saved body.':'Saved response source. Scripts are displayed as text.','panel-note'),node('pre',data.text));
 }
}
$('filters').addEventListener('submit',event=>event.preventDefault());
let searchTimer;
$('query').addEventListener('input',()=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>{currentPage=1;pages().catch(fail);},250);});
for(const id of ['kind','state'])$(id).addEventListener('change',()=>{currentPage=1;pages().catch(fail);});
$('generation').addEventListener('change',()=>{currentPage=1;selectedUrl=null;detail=null;$('inspector-content').hidden=true;$('inspector-empty').hidden=false;refresh();});
$('refresh').addEventListener('click',refresh);
$('previous').addEventListener('click',()=>{currentPage--;pages().catch(fail);});
$('next').addEventListener('click',()=>{currentPage++;pages().catch(fail);});
const tabs=[...document.querySelectorAll('[data-tab]')];
for(const button of tabs){button.addEventListener('click',()=>{activeTab=button.dataset.tab;renderPanel().catch(fail);});button.addEventListener('keydown',event=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){event.preventDefault();let index=tabs.indexOf(button);index=event.key==='Home'?0:event.key==='End'?tabs.length-1:(index+(event.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;tabs[index].click();tabs[index].focus();}});}
refresh();setInterval(()=>{if(!document.hidden)refresh();},10000);

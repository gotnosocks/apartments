"""Shared style, chart code and data for the three conference pages."""

import json
from pathlib import Path

HERE = Path(__file__).parent
T = json.loads((HERE / "terms.json").read_text())

FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500'
    '&family=IBM+Plex+Sans:wght@400;500;600&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;'
    '1,8..60,400&display=swap">'
)

CSS = """
/* Layout: one reading column, ~68ch, with wide figures allowed to break out to 920px. */
:root{
  --bg:#F4F6F8; --surface:#FFFFFF; --fg:#17202B; --muted:#586476; --rule:#D6DCE4;
  --accent:#0A6A70; --accent-soft:rgba(10,106,112,.12); --alt:#9A5806; --alt-soft:rgba(154,88,6,.14);
  --good:#2F7D32; --bad:#B23A2E; --grid:rgba(23,32,43,.08);
  --serif:"Source Serif 4", Georgia, "Times New Roman", serif;
  --sans:"IBM Plex Sans", "Helvetica Neue", Arial, sans-serif;
  --mono:"IBM Plex Mono", ui-monospace, Menlo, Consolas, monospace;
}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){
  --bg:#10151C; --surface:#161D26; --fg:#E4E9EF; --muted:#97A3B4; --rule:#2B3542;
  --accent:#4CBFC4; --accent-soft:rgba(76,191,196,.16); --alt:#E5A54C; --alt-soft:rgba(229,165,76,.16);
  --good:#7CC47F; --bad:#EE8A7E; --grid:rgba(228,233,239,.08); color-scheme:dark}}
:root[data-theme="dark"]{
  --bg:#10151C; --surface:#161D26; --fg:#E4E9EF; --muted:#97A3B4; --rule:#2B3542;
  --accent:#4CBFC4; --accent-soft:rgba(76,191,196,.16); --alt:#E5A54C; --alt-soft:rgba(229,165,76,.16);
  --good:#7CC47F; --bad:#EE8A7E; --grid:rgba(228,233,239,.08); color-scheme:dark}
body{background:var(--bg);color:var(--fg);font-family:var(--serif);font-size:17.5px;line-height:1.6;
  padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));
  padding-block:40px 80px}
main{max-width:920px;margin:0 auto;display:flex;flex-direction:column;gap:0}
.col{max-width:68ch;width:100%;margin:0 auto}
header.top{max-width:68ch;margin:0 auto 28px;width:100%}
.kicker{font-family:var(--sans);font-size:12.5px;letter-spacing:.09em;text-transform:uppercase;color:var(--accent);font-weight:600}
h1{font-family:var(--sans);font-weight:600;font-size:clamp(28px,4.4vw,40px);line-height:1.15;margin:.35em 0 .3em;text-wrap:balance;letter-spacing:-.01em}
h2{font-family:var(--sans);font-weight:600;font-size:22px;line-height:1.25;margin:2.1em 0 .5em;text-wrap:balance}
h3{font-family:var(--sans);font-weight:600;font-size:17px;margin:1.6em 0 .3em}
p{margin:.7em 0}
.lede{font-size:20px;line-height:1.5;color:var(--fg)}
.byline{font-family:var(--sans);font-size:14px;color:var(--muted)}
a{color:var(--accent);text-underline-offset:2px}
a:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.num,td.n,th.n{font-family:var(--mono);font-variant-numeric:tabular-nums;font-size:.86em}
.muted{color:var(--muted)}
.tw{overflow-x:auto;margin:1em 0;max-width:100%}
table{border-collapse:collapse;width:100%;font-family:var(--sans);font-size:14.5px;line-height:1.4}
th{text-align:left;font-weight:600;color:var(--muted);font-size:12.5px;letter-spacing:.04em;text-transform:uppercase;border-bottom:1.5px solid var(--fg);padding:6px 10px 6px 0}
td{border-bottom:1px solid var(--rule);padding:7px 10px 7px 0;vertical-align:top}
td.n,th.n{text-align:right;white-space:nowrap}
.tw td:first-child{min-width:13em}
caption{caption-side:bottom;text-align:left;font-size:13px;color:var(--muted);padding-top:8px;font-family:var(--sans)}
figure{margin:1.6em auto;max-width:920px;width:100%}
figure .frame{background:var(--surface);border:1px solid var(--rule);border-radius:6px;padding:16px 16px 8px}
figcaption{font-family:var(--sans);font-size:13.5px;color:var(--muted);margin-top:8px;max-width:68ch;line-height:1.45}
figcaption b{color:var(--fg);font-weight:600}
svg text{font-family:var(--sans);fill:var(--muted);font-size:12px}
svg .lab{fill:var(--fg);font-size:12.5px}
svg .grid{stroke:var(--grid);stroke-width:1}
svg .axis{stroke:var(--rule);stroke-width:1}
svg .zero{stroke:var(--muted);stroke-width:1;stroke-dasharray:3 3}
svg .band-a{fill:var(--accent-soft)} svg .line-a{stroke:var(--accent);fill:none;stroke-width:2}
svg .dot-a{fill:var(--accent)} svg .dot-b{fill:var(--alt)}
svg .bar-a{stroke:var(--accent);stroke-width:2.2} svg .bar-b{stroke:var(--alt);stroke-width:2.2}
svg .line-b{stroke:var(--alt);fill:none;stroke-width:2}
.legend{display:flex;flex-wrap:wrap;gap:6px 18px;font-family:var(--sans);font-size:13px;color:var(--muted);margin:2px 0 6px}
.legend span{display:inline-flex;align-items:center;gap:6px}
.sw{width:14px;height:3px;border-radius:2px;display:inline-block}
.sw.a{background:var(--accent)} .sw.b{background:var(--alt)}
.card{background:var(--surface);border:1px solid var(--rule);border-radius:6px;padding:16px 20px;margin:1.2em 0}
.card h3{margin-top:0}
.pill{display:inline-block;font-family:var(--sans);font-size:11.5px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;padding:2px 8px;border-radius:999px;white-space:nowrap}
.pill.keep{background:var(--accent-soft);color:var(--accent)}
.pill.drop{background:rgba(178,58,46,.12);color:var(--bad)}
.pill.open{background:var(--alt-soft);color:var(--alt)}
.eq{font-family:var(--mono);font-size:14px;background:var(--surface);border:1px solid var(--rule);border-radius:6px;padding:14px 16px;overflow-x:auto;white-space:pre;line-height:1.7}
.stack{display:flex;height:34px;border-radius:4px;overflow:hidden;border:1px solid var(--rule);font-family:var(--sans);font-size:12px}
.stack div{display:flex;align-items:center;justify-content:center;color:var(--bg);font-weight:600;white-space:nowrap;overflow:hidden}
ol.refs{font-size:15px;padding-left:1.4em} ol.refs li{margin:.35em 0}
.qa dt{font-family:var(--sans);font-weight:600;margin-top:1.2em}
.qa dd{margin:.3em 0 0 0}
.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin:1.4em 0}
.facts div{background:var(--surface);border:1px solid var(--rule);border-radius:6px;padding:12px 14px;min-width:0}
.facts b{display:block;font-family:var(--mono);font-size:21px;font-weight:500;color:var(--fg)}
.facts span{font-family:var(--sans);font-size:13px;color:var(--muted);line-height:1.35;display:block;margin-top:2px}
footer{max-width:68ch;margin:3em auto 0;font-family:var(--sans);font-size:13px;color:var(--muted);border-top:1px solid var(--rule);padding-top:14px;width:100%}
@media (max-width:560px){body{font-size:16.5px}.lede{font-size:18px}table{font-size:13px}}
"""


def elev_curve():
    rows = [[1, 0, 0, 0]]
    for k in range(2, 48):
        v = T[f"unit:elev_f{k}"]["f"]
        rows.append([k, v[0], v[1], v[2]])
    return rows


def walk_curve():
    rows = [[1, 0, 0, 0]]
    for k in range(2, 7):
        v = T[f"unit:walkup_f{k}"]["f"]
        rows.append([k, v[0], v[1], v[2]])
    return rows


def forest_rows(spec):
    out = []
    for label, key, scale in spec:
        r = T[key]
        if scale == "elastic":
            f = [x / 100 for x in r["f"][3:6]]
            m = [x / 100 for x in r["m"][3:6]]
        else:
            f, m = r["f"][:3], r["m"][:3]
        out.append({"label": label, "f": f, "m": m})
    return out


JS = r"""
const NS='http://www.w3.org/2000/svg';
function el(t,a,p){const e=document.createElementNS(NS,t);for(const k in a)e.setAttribute(k,a[k]);if(p)p.appendChild(e);return e}
function txt(p,x,y,s,a){const e=el('text',Object.assign({x,y},a||{}),p);e.textContent=s;return e}
function niceTicks(lo,hi,n){const span=hi-lo,step0=span/n,mag=Math.pow(10,Math.floor(Math.log10(step0)));
  const step=[1,2,2.5,5,10].map(m=>m*mag).find(s=>s>=step0);const out=[];for(let v=Math.ceil(lo/step)*step;v<=hi+1e-9;v+=step)out.push(+v.toFixed(6));return out}
function floorChart(id,elev,walk){
  const host=document.getElementById(id);const W=860,H=340,L=52,R=20,Tp=14,B=44;
  const s=el('svg',{viewBox:`0 0 ${W} ${H}`,width:'100%',role:'img','aria-label':'Rent premium by floor'},host);
  const lx=v=>Math.log(v),x0=lx(1),x1=lx(48);const X=v=>L+(lx(v)-x0)/(x1-x0)*(W-L-R);
  const ylo=-2,yhi=21;const Y=v=>Tp+(yhi-v)/(yhi-ylo)*(H-Tp-B);
  for(const t of [0,5,10,15,20]){el('line',{x1:L,x2:W-R,y1:Y(t),y2:Y(t),class:t===0?'zero':'grid'},s);txt(s,L-8,Y(t)+4,(t>0?'+':'')+t+'%',{'text-anchor':'end'})}
  for(const f of [1,2,3,5,10,20,30,47]){el('line',{x1:X(f),x2:X(f),y1:Y(yhi),y2:Y(ylo),class:'grid'},s);txt(s,X(f),H-B+18,f===47?'47+':String(f),{'text-anchor':'middle'})}
  txt(s,(L+W-R)/2,H-6,'Floor (log scale)',{'text-anchor':'middle'});
  let d='';elev.forEach((r,i)=>{d+=(i?'L':'M')+X(r[0])+' '+Y(r[3])});for(let i=elev.length-1;i>=0;i--)d+='L'+X(elev[i][0])+' '+Y(elev[i][2]);el('path',{d:d+'Z',class:'band-a'},s);
  el('path',{d:elev.map((r,i)=>(i?'L':'M')+X(r[0])+' '+Y(r[1])).join(''),class:'line-a'},s);
  el('path',{d:walk.map((r,i)=>(i?'L':'M')+X(r[0])+' '+Y(r[1])).join(''),class:'line-b'},s);
  walk.forEach(r=>el('circle',{cx:X(r[0]),cy:Y(r[1]),r:2.6,class:'dot-b'},s));
  const last=elev[elev.length-1];txt(s,X(last[0])-6,Y(last[1])-10,'elevator',{'text-anchor':'end',class:'lab'});
  txt(s,X(6)+8,Y(walk[5][1])+16,'walk-up',{class:'lab'});
}
function forest(id,rows,opts){
  const host=document.getElementById(id);const W=860,rowH=30,Tp=8,B=40,L=opts.left||250,R=24;const H=Tp+B+rows.length*rowH;
  const s=el('svg',{viewBox:`0 0 ${W} ${H}`,width:'100%',role:'img','aria-label':opts.aria||'Premiums with 90% intervals'},host);
  let lo=Math.min(0,...rows.flatMap(r=>[r.f[1],r.m?r.m[1]:r.f[1]])),hi=Math.max(0,...rows.flatMap(r=>[r.f[2],r.m?r.m[2]:r.f[2]]));
  const pad=(hi-lo)*.06;lo-=pad;hi+=pad;const X=v=>L+(v-lo)/(hi-lo)*(W-L-R);
  for(const t of niceTicks(lo,hi,6)){el('line',{x1:X(t),x2:X(t),y1:Tp,y2:H-B+4,class:t===0?'zero':'grid'},s);txt(s,X(t),H-B+20,(t>0?'+':'')+t+(opts.unit||''),{'text-anchor':'middle'})}
  if(opts.xlabel)txt(s,(L+W-R)/2,H-6,opts.xlabel,{'text-anchor':'middle'});
  rows.forEach((r,i)=>{const y=Tp+i*rowH+rowH/2;txt(s,L-12,y+4,r.label,{'text-anchor':'end',class:'lab'});
    const ya=r.m?y-5:y;el('line',{x1:X(r.f[1]),x2:X(r.f[2]),y1:ya,y2:ya,class:'bar-a'},s);el('circle',{cx:X(r.f[0]),cy:ya,r:4,class:'dot-a'},s);
    if(r.m){el('line',{x1:X(r.m[1]),x2:X(r.m[2]),y1:y+5,y2:y+5,class:'bar-b'},s);el('rect',{x:X(r.m[0])-3.5,y:y+1.5,width:7,height:7,class:'dot-b'},s)}});
}
"""


def page(title, desc_meta, body, data_js):
    return f"""<title>{title}</title>
<meta name="claude:viewport-fit-sides" content="cover">
<meta name="description" content="{desc_meta}">
{FONTS}
<style>{CSS}</style>
{body}
<script>{JS}
{data_js}</script>
"""


def data_js():
    unit = forest_rows([
        ("In-unit laundry", "unit:laundry_in_unit", "pct"),
        ("Laundry in building", "unit:laundry_in_building", "pct"),
        ("Dishwasher", "unit:dishwasher", "pct"),
        ("Private garden / outdoor", "unit:garden", "pct"),
        ("Penthouse (over floor curve)", "unit:penthouse", "pct"),
        ("Top floor, elevator bldg", "unit:elev_top", "pct"),
        ("Below grade / lower level", "unit:lower", "pct"),
        ("Size not stated", "unit:size_unknown", "pct"),
    ])
    bld = forest_rows([
        ("Full-time doorman", "bld:doorman_full", "pct"),
        ("Condo building", "bld:condo", "pct"),
        ("Part-time doorman", "bld:doorman_part", "pct"),
        ("Gym", "bld:gym", "pct"),
        ("Built 2010 or later", "bld:built_2010_on", "pct"),
        ("Built before 1900", "bld:built_pre1900", "pct"),
        ("Major alteration since 2000", "bld:altered_2000_on", "pct"),
        ("Elevator", "bld:elevator", "pct"),
        ("Virtual doorman", "bld:doorman_virtual", "pct"),
        ("Ground-floor retail", "bld:retail", "pct"),
        ("Faces a through truck route", "bld:truck_through", "pct"),
        ("Rent stabilized (ad says)", "flag:rent_stabilized", "pct"),
        ("Income restricted", "flag:income_restricted", "pct"),
    ])
    return (
        f"const ELEV={json.dumps(elev_curve())};const WALK={json.dumps(walk_curve())};"
        f"const UNIT={json.dumps(unit)};const BLD={json.dumps(bld)};"
    )

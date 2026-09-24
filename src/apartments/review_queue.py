"""Residual review queue ranked on unit-level deviation from the selected fit.

Report-only: reads saved residuals, group effects and source rows from the
explicitly selected PyMC fit and publishes a small immutable bundle plus a
self-contained HTML page. It never opens the posterior draws, fits, scrapes or
changes the selection.

Why ``unit_effect + residual``: the selected fits have a per-unit random
effect and most units have one or two observations. For such units the split
between "unit effect" and "residual" is set by the prior variance ratio, not by
data, so ranking on the residual alone under-flags rarely listed apartments.
The unit-level deviation is the departure of the ask from what the building,
features and calendar month predict before any apartment-specific offset.
"""
from __future__ import annotations

import html
import json
import math
from pathlib import Path
from urllib.parse import urlparse

from .corrections import canonical
from .main_analysis import DEFAULT_SELECTION, ROOT, load_selection, resolve_path
from .research_pipeline import _verified_bundle, digest, publish_bundle

VERSION = 'bayesian-unit-deviation-review-queue-v1'
RANKING = 'absolute unit-level deviation: |residual_log + unit_effect_median|'
INTERPRETATION = (
    'Unit-level deviation is the log difference between the advertised ask and the '
    'fitted median with the apartment-specific unit effect removed (building, feature, '
    'trend and season contributions retained). It is an in-sample review signal for '
    'source errors, omitted features, identity or price-basis problems; it is not a '
    'bargain score. Dollar values remove the posterior-median unit effect from the '
    'posterior-median fitted rent, which is an approximation of the median without '
    'that effect.')
ADVERTISEMENT_URL = 'https://streeteasy.com/rental/'
QUEUE_FILE = 'queue.jsonl'
PAGE_FILE = 'queue.html'
COLUMNS = ['rank', 'audit_id', 'unit_id', 'building', 'unit_label', 'source_listing_id',
    'advertisement_url', 'canonical_unit_url', 'period', 'price_basis', 'current_capture',
    'bedrooms', 'bathrooms', 'square_feet', 'listed_floor', 'asking_rent', 'fitted_rent',
    'latent_rent_lower_95', 'latent_rent_upper_95', 'residual_log', 'residual_dollars',
    'residual_percent', 'unit_effect_log', 'unit_effect_lower_95', 'unit_effect_upper_95',
    'building_effect_log', 'unit_deviation_log', 'fitted_rent_without_unit',
    'unit_deviation_dollars', 'unit_deviation_percent', 'unit_observations',
    'residual_rank', 'source_review', 'description']


def _records(data):
    return [json.loads(line) for line in data.decode().splitlines() if line.strip()]


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _number(value):
    return float(value) if _finite(value) else None


def _unit_label(url):
    if not isinstance(url, str):
        return None
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname not in {'streeteasy.com', 'www.streeteasy.com'}:
        return None
    parts = [p for p in parsed.path.split('/') if p]
    return parts[-1] if len(parts) >= 3 and parts[0] == 'building' else None


def _advertisement_url(listing_id):
    text = str(listing_id) if listing_id is not None else ''
    return ADVERTISEMENT_URL + text if text.isdigit() else None


def _descriptions(dataset, evidence):
    """Latest archived description per audit ID, hash-verified, without lineage replay."""
    manifest, files = _verified_bundle(evidence, retain={'evidence.jsonl'})
    latest = {}
    for record in _records(files['evidence.jsonl']):
        identity, text = record.get('audit_id'), record.get('description')
        if not identity or not isinstance(text, str) or not text.strip():
            continue
        stamp = record.get('source_collected_at') or ''
        if identity not in latest or stamp > latest[identity][0]:
            latest[identity] = (stamp, ' '.join(text.split()))
    return manifest, {k: v[1] for k, v in latest.items()}


def _notes(selection, experiment, dataset):
    """Existing per-observation source notes; failures are reported, not fatal."""
    notes, warnings = {}, []
    if not (selection.get('source_review') or selection.get('source_issues')):
        return notes, warnings
    if not selection.get('evidence'):
        return notes, ['Selected source annotations lack a description archive; notes omitted']
    evidence = resolve_path(selection['evidence'])
    if selection.get('source_review'):
        try:
            from .bayesian_source_review import load_source_review
            notes.update(load_source_review(experiment, dataset, resolve_path(selection['source_review']), evidence=evidence))
        except (OSError, ValueError, KeyError, TypeError) as error:
            warnings.append('Source review notes unavailable: ' + str(error))
    if selection.get('source_issues'):
        try:
            from .source_issues import load_source_issues, merge_notes
            notes = merge_notes(notes, load_source_issues(dataset, resolve_path(selection['source_issues']), evidence=evidence))
        except (OSError, ValueError, KeyError, TypeError) as error:
            warnings.append('Source issue notes unavailable: ' + str(error))
    return notes, warnings


def build_rows(residuals, effects, source, *, notes=None, descriptions=None, snippet=240):
    """Join saved residuals with group effects and source rows; rank on unit deviation."""
    notes, descriptions = notes or {}, descriptions or {}
    units = {e['id']: e['log_effect'] for e in effects if e.get('kind') == 'unit'}
    buildings = {e['id']: e['log_effect'] for e in effects if e.get('kind') == 'building'}
    rows_by_id = {r['audit_id']: r for r in source}
    counts = {}
    for residual in residuals:
        counts[residual['unit_id']] = counts.get(residual['unit_id'], 0) + 1
    rows = []
    for residual in residuals:
        identity = residual['audit_id']
        row = rows_by_id.get(identity)
        if row is None:
            raise ValueError('Residual has no source row: ' + identity)
        unit = units.get(residual['unit_id'])
        if unit is None:
            raise ValueError('Residual unit has no saved effect: ' + residual['unit_id'])
        building = buildings.get(residual['building'])
        if building is None:
            raise ValueError('Residual building has no saved effect: ' + residual['building'])
        for name in ('asking_rent', 'fitted_rent', 'residual_log'):
            if not _finite(residual.get(name)) or (name != 'residual_log' and residual[name] <= 0):
                raise ValueError(f'Residual {identity} has invalid {name}')
        ask, fitted, residual_log = residual['asking_rent'], residual['fitted_rent'], residual['residual_log']
        unit_effect = unit['median']
        deviation = residual_log + unit_effect
        without_unit = fitted * math.exp(-unit_effect)
        note = notes.get(identity)
        text = descriptions.get(identity)
        rows.append({
            'audit_id': identity, 'unit_id': residual['unit_id'], 'building': residual['building'],
            'unit_label': _unit_label(row.get('canonical_unit_url')),
            'source_listing_id': str(residual.get('source_listing_id') or row.get('source_listing_id') or ''),
            'advertisement_url': _advertisement_url(residual.get('source_listing_id') or row.get('source_listing_id')),
            'canonical_unit_url': row.get('canonical_unit_url'),
            'period': str(residual.get('period') or row.get('period')),
            'price_basis': row.get('analysis_price_basis'),
            'current_capture': row.get('analysis_price_basis') == 'current_capture_gross_ask',
            'bedrooms': _number(row.get('bedrooms')), 'bathrooms': _number(row.get('bathrooms')),
            'square_feet': _number(row.get('square_feet')), 'listed_floor': _number(row.get('listed_floor')),
            'asking_rent': ask, 'fitted_rent': fitted,
            'latent_rent_lower_95': _number(residual.get('latent_rent_lower_95')),
            'latent_rent_upper_95': _number(residual.get('latent_rent_upper_95')),
            'residual_log': residual_log, 'residual_dollars': ask - fitted,
            'residual_percent': 100 * (ask / fitted - 1),
            'unit_effect_log': unit_effect, 'unit_effect_lower_95': unit['lower_95'],
            'unit_effect_upper_95': unit['upper_95'], 'building_effect_log': building['median'],
            'unit_deviation_log': deviation, 'fitted_rent_without_unit': without_unit,
            'unit_deviation_dollars': ask - without_unit,
            'unit_deviation_percent': 100 * (ask / without_unit - 1),
            'unit_observations': counts[residual['unit_id']],
            'source_review': note['kind'] if note else '',
            'description': (text[:snippet] + ('…' if len(text) > snippet else '')) if text else None})
    by_residual = sorted(rows, key=lambda r: (-abs(r['residual_log']), r['audit_id']))
    for position, row in enumerate(by_residual, 1):
        row['residual_rank'] = position
    rows.sort(key=lambda r: (-abs(r['unit_deviation_log']), r['audit_id']))
    for position, row in enumerate(rows, 1):
        row['rank'] = position
    return [{name: row.get(name) for name in COLUMNS} for row in rows]


def summarize(rows, top=100):
    def median(values):
        values = sorted(values)
        n = len(values)
        return None if not n else values[n // 2] if n % 2 else (values[n // 2 - 1] + values[n // 2]) / 2
    top_deviation = {r['audit_id'] for r in rows[:top]}
    top_residual = {r['audit_id'] for r in sorted(rows, key=lambda r: r['residual_rank'])[:top]}
    singles = [r for r in rows if r['unit_observations'] == 1]
    return {
        'rows': len(rows), 'units': len({r['unit_id'] for r in rows}),
        'buildings': len({r['building'] for r in rows}),
        'current_rows': sum(r['current_capture'] for r in rows),
        'single_observation_rows': len(singles),
        'median_absolute_residual_log': median([abs(r['residual_log']) for r in rows]),
        'median_absolute_unit_deviation_log': median([abs(r['unit_deviation_log']) for r in rows]),
        'median_residual_share_of_deviation_single_observation_units': median(
            [abs(r['residual_log']) / abs(r['unit_deviation_log']) for r in singles if abs(r['unit_deviation_log']) > 1e-9]),
        'top_n': top,
        'top_n_overlap_between_rankings': len(top_deviation & top_residual),
        'top_n_single_observation_units_by_deviation': sum(r['unit_observations'] == 1 for r in rows[:top]),
        'top_n_single_observation_units_by_residual': sum(
            r['unit_observations'] == 1 for r in sorted(rows, key=lambda r: r['residual_rank'])[:top]),
    }


def page_rows(rows, limit):
    """Bounded page subset: top by deviation, top by residual and every current capture."""
    keep = {r['audit_id'] for r in rows[:limit]}
    keep |= {r['audit_id'] for r in sorted(rows, key=lambda r: r['residual_rank'])[:limit]}
    keep |= {r['audit_id'] for r in rows if r['current_capture']}
    return [r for r in rows if r['audit_id'] in keep]


def render_page(rows, summary, bindings, *, total=None):
    """Self-contained HTML: embedded rows, client-side sort/filter, external links only to StreetEasy."""
    payload = json.dumps(rows, separators=(',', ':')).replace('</', '<\\/')
    title = 'Residual review queue — ' + html.escape(Path(bindings['experiment']).name)
    total = len(rows) if total is None else total
    scope = (f'This page embeds {len(rows):,} of {total:,} fitted observations: the largest unit-level deviations, '
             f'the largest residuals and every saved current capture. The complete ranking is in {QUEUE_FILE}.')
    return _PAGE_TEMPLATE.replace('__TITLE__', title).replace('__ROWS__', payload) \
        .replace('__SCOPE__', html.escape(scope)).replace('__TOTAL__', str(total)) \
        .replace('__SUMMARY__', html.escape(json.dumps(summary, indent=1))) \
        .replace('__BINDINGS__', html.escape(json.dumps({k: v for k, v in bindings.items() if k != 'files'}, indent=1))) \
        .replace('__INTERPRETATION__', html.escape(INTERPRETATION))


QUEUE_ROOT = Path('data/model/review-queue')


def default_output(selection=DEFAULT_SELECTION, *, root=ROOT):
    """Deterministic bundle location for the current selection and queue version.

    The name binds the experiment, its fit manifest hash and this queue version,
    so a new selection or a changed queue implementation publishes elsewhere
    while an unchanged selection verifies and reuses the existing bundle.
    """
    selected, experiment, _ = load_selection(selection, root=root)
    tag = VERSION.rsplit('-', 1)[-1]
    return Path(root) / QUEUE_ROOT / f"{experiment.name}-{selected['fit_manifest_sha256'][:12]}-{tag}"


def locate(selection=DEFAULT_SELECTION, *, root=ROOT):
    """Return ``(directory, manifest)`` for a complete bundle bound to the selection, else ``None``."""
    selected, experiment, dataset = load_selection(selection, root=root)
    directory = default_output(selection, root=root)
    marker = directory / 'complete.json'
    if not marker.is_file() or marker.is_symlink():
        return None
    manifest = json.loads(marker.read_text())
    expected = {'version': VERSION, 'fit_manifest_sha256': selected['fit_manifest_sha256'],
                'source_manifest_sha256': selected['source_manifest_sha256']}
    if any(manifest.get(k) != v for k, v in expected.items()) or not {QUEUE_FILE, PAGE_FILE, 'summary.json'} <= set(manifest.get('files', {})):
        raise ValueError('Review queue bundle does not match the selected fit: ' + str(directory))
    return directory, manifest


def load_queue(directory):
    """Hash-verified rows and summary from a published bundle."""
    manifest, files = _verified_bundle(directory, retain={QUEUE_FILE, 'summary.json'})
    return _records(files[QUEUE_FILE]), json.loads(files['summary.json']), manifest


def build_review_queue(output=None, *, selection=DEFAULT_SELECTION, root=ROOT, include_descriptions=True, top=100,
                       page_limit=2500):
    selected, experiment, dataset = load_selection(selection, root=root)
    output = default_output(selection, root=root) if output is None else Path(output)
    fit_manifest, fit_files = _verified_bundle(experiment / 'fit', retain={'residuals.jsonl', 'group-effects.jsonl'})
    source_manifest, source_files = _verified_bundle(dataset, retain={'observations.jsonl'})
    residuals = _records(fit_files['residuals.jsonl'])
    effects = _records(fit_files['group-effects.jsonl'])
    source = _records(source_files['observations.jsonl'])
    descriptions, evidence_manifest, warnings = {}, None, []
    if include_descriptions and selected.get('evidence'):
        try:
            evidence_manifest, descriptions = _descriptions(dataset, resolve_path(selected['evidence'], root))
        except (OSError, ValueError, KeyError) as error:
            warnings.append('Descriptions unavailable: ' + str(error))
    notes, note_warnings = _notes(selected, experiment, dataset)
    warnings.extend(note_warnings)
    rows = build_rows(residuals, effects, source, notes=notes, descriptions=descriptions)
    embedded = page_rows(rows, page_limit)
    summary = {**summarize(rows, top=top), 'ranking': RANKING, 'interpretation': INTERPRETATION,
               'source_notes': len(notes), 'descriptions': sum(r['description'] is not None for r in rows),
               'page_rows': len(embedded), 'page_limit': page_limit, 'warnings': warnings}
    bindings = {'version': VERSION, 'selection': str(Path(selection)), 'experiment': str(experiment), 'dataset': str(dataset),
        'fit_manifest_sha256': digest(experiment / 'fit/complete.json'),
        'source_manifest_sha256': digest(dataset / 'complete.json'),
        'residuals_sha256': fit_manifest['files']['residuals.jsonl'],
        'group_effects_sha256': fit_manifest['files']['group-effects.jsonl'],
        'source_observations_sha256': source_manifest['files']['observations.jsonl'],
        'evidence_manifest_sha256': digest(resolve_path(selected['evidence'], root) / 'complete.json')
            if evidence_manifest is not None else None,
        'rows': len(rows), 'ranking': RANKING}
    files = {QUEUE_FILE: ''.join(canonical(r) + '\n' for r in rows),
             'summary.json': canonical(summary) + '\n',
             PAGE_FILE: render_page(embedded, summary, bindings, total=len(rows))}
    manifest = publish_bundle(output, files, bindings)
    return {**summary, 'output': str(output), 'files': sorted(manifest['files'])}


def serve(directory=None, *, selection=None, root=ROOT, host='127.0.0.1', port=8767, listen=None):
    """Serve the published queue page read-only; no scraping, fitting or edits.

    With ``selection`` the bundle is resolved from the selection file on every
    request, so a new selection or rebuilt queue is served without a restart.
    """
    from flask import Flask, abort, send_from_directory
    from waitress import serve as waitress_serve
    if (directory is None) == (selection is None):
        raise ValueError('Serve either a bundle directory or a selection file')
    fixed = Path(directory).resolve() if directory else None
    if fixed is not None and not (fixed / PAGE_FILE).is_file():
        raise ValueError('No published review queue page in ' + str(fixed))
    app = Flask('review-queue')

    def current():
        if fixed is not None:
            return fixed
        try:
            found = locate(selection, root=root)
        except (OSError, ValueError, KeyError):
            found = None
        return found[0].resolve() if found else None

    @app.get('/')
    def index():
        directory = current()
        if directory is None:
            return ('<!doctype html><title>Review queue</title><p>No review queue bundle is published for the '
                    'selected fit. Run <code>apartments build-review-queue</code>.</p>', 503)
        return send_from_directory(directory, PAGE_FILE)

    @app.get('/<name>')
    def artifact(name):
        directory = current()
        if directory is None or name not in {QUEUE_FILE, PAGE_FILE, 'summary.json', 'complete.json'}:
            abort(404)
        return send_from_directory(directory, name)

    waitress_serve(app, threads=2, **({'listen': listen} if listen else {'host': host, 'port': port}))


_PAGE_TEMPLATE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--line:#d8dde3;--muted:#6b7280;--pos:#b42318;--neg:#027a48;--bg:#fafbfc}
body{font:14px/1.4 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:var(--bg);color:#111}
header{padding:14px 20px;border-bottom:1px solid var(--line);background:#fff}
h1{font-size:18px;margin:0 0 4px}header p{margin:2px 0;color:var(--muted)}
.controls{display:flex;flex-wrap:wrap;gap:12px 18px;padding:12px 20px;background:#fff;border-bottom:1px solid var(--line);align-items:end}
.controls label{display:flex;flex-direction:column;font-size:12px;color:var(--muted);gap:3px}
.controls input,.controls select{font:inherit;padding:4px 6px;border:1px solid var(--line);border-radius:4px;min-width:90px}
.controls .check{flex-direction:row;align-items:center;gap:6px;font-size:13px;color:#111}
main{padding:12px 20px;overflow-x:auto}
table{border-collapse:collapse;width:100%;background:#fff;font-size:13px}
th,td{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top;white-space:nowrap}
th{position:sticky;top:0;background:#f3f4f6;cursor:pointer;user-select:none;font-weight:600}
th.sorted::after{content:" ▾";color:var(--muted)}th.sorted.asc::after{content:" ▴"}
td.num{text-align:right;font-variant-numeric:tabular-nums}
td.pos{color:var(--pos)}td.neg{color:var(--neg)}
td.desc{white-space:normal;max-width:420px;color:#374151;font-size:12px}
a{color:#1d4ed8;text-decoration:none}a:hover{text-decoration:underline}
.tag{display:inline-block;padding:1px 6px;border-radius:10px;background:#eef2ff;color:#3730a3;font-size:11px}
.warn{background:#fef3c7;color:#92400e}
details{margin:8px 20px}summary{cursor:pointer;color:var(--muted)}pre{font-size:12px;background:#fff;padding:10px;border:1px solid var(--line);overflow:auto}
.count{color:var(--muted);font-size:12px;margin-left:auto}
</style></head><body>
<header><h1>__TITLE__</h1>
<p>Ranked on unit-level deviation = residual + unit effect. Percent columns compare the ask with the fitted median; “without unit” removes the apartment-specific offset.</p>
<p>__INTERPRETATION__</p>
<p>__SCOPE__</p></header>
<div class="controls">
 <label>Scope<select id="scope"><option value="all">All fitted observations</option><option value="current">Saved current captures</option><option value="historical">Historical initial asks</option></select></label>
 <label>Direction<select id="dir"><option value="abs">Largest |deviation|</option><option value="above">Ask above fitted</option><option value="below">Ask below fitted</option></select></label>
 <label>Min |deviation| %<input id="minpct" type="number" value="0" step="1" min="0"></label>
 <label>From year<input id="year" type="number" value="2010" min="2000" max="2030"></label>
 <label>Bedrooms<select id="beds"><option value="">Any</option><option>0</option><option>1</option><option>2</option><option>3</option><option value="4+">4+</option></select></label>
 <label>Building / ad / unit<input id="search" type="search" placeholder="filter text"></label>
 <label class="check"><input id="oneper" type="checkbox" checked>One row per unit</label>
 <label>Rows<select id="limit"><option>50</option><option selected>200</option><option>1000</option><option value="0">All</option></select></label>
 <span class="count" id="count"></span>
</div>
<main><table id="t"><thead><tr>
<th data-k="rank">#</th><th data-k="building">Building</th><th data-k="unit_label">Unit</th><th data-k="period">Month</th>
<th data-k="bedrooms">Bd</th><th data-k="bathrooms">Ba</th><th data-k="square_feet">Sq ft</th><th data-k="listed_floor">Fl</th>
<th data-k="asking_rent">Ask</th><th data-k="fitted_rent_without_unit">Fitted w/o unit</th><th data-k="unit_deviation_percent">Deviation %</th><th data-k="unit_deviation_dollars">Deviation $</th>
<th data-k="fitted_rent">Fitted</th><th data-k="residual_percent">Residual %</th><th data-k="unit_effect_log">Unit eff</th><th data-k="building_effect_log">Bldg eff</th>
<th data-k="unit_observations">Obs</th><th data-k="residual_rank">Resid. rank</th><th data-k="source_review">Review</th><th>Links</th><th data-k="description">Description</th>
</tr></thead><tbody></tbody></table></main>
<details><summary>Summary and bindings</summary><pre>__SUMMARY__</pre><pre>__BINDINGS__</pre></details>
<script>
const ROWS=__ROWS__;
const $=id=>document.getElementById(id);
let sortKey='rank',asc=true;
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=v=>v==null?'':'$'+Math.round(v).toLocaleString();
const pct=v=>v==null?'':(v>0?'+':'')+v.toFixed(1)+'%';
const num=(v,d)=>v==null?'':Number(v).toFixed(d);
const safe=u=>typeof u==='string'&&/^https:\/\/(www\.)?streeteasy\.com\//.test(u)?u:null;
function filtered(){
 const scope=$('scope').value,dir=$('dir').value,minp=+$('minpct').value||0,year=+$('year').value||0,beds=$('beds').value,q=$('search').value.trim().toLowerCase();
 let rows=ROWS.filter(r=>{
  if(scope==='current'&&!r.current_capture)return false;
  if(scope==='historical'&&r.current_capture)return false;
  if(dir==='above'&&!(r.unit_deviation_log>0))return false;
  if(dir==='below'&&!(r.unit_deviation_log<0))return false;
  if(Math.abs(r.unit_deviation_percent)<minp)return false;
  if(year&&+String(r.period).slice(0,4)<year)return false;
  if(beds==='4+'){if(!(r.bedrooms>=4))return false}else if(beds!==''&&r.bedrooms!==+beds)return false;
  if(q&&!(String(r.building).toLowerCase().includes(q)||String(r.unit_label||'').toLowerCase().includes(q)||String(r.source_listing_id).includes(q)||String(r.canonical_unit_url||'').toLowerCase().includes(q)))return false;
  return true});
 rows.sort((a,b)=>{let x=a[sortKey],y=b[sortKey];if(x==null)return 1;if(y==null)return -1;
  if(typeof x==='number'&&typeof y==='number'){if(sortKey==='unit_deviation_percent'||sortKey==='unit_deviation_dollars'||sortKey==='residual_percent'||sortKey==='unit_effect_log'||sortKey==='building_effect_log'){x=Math.abs(x);y=Math.abs(y)}return asc?x-y:y-x}
  x=String(x);y=String(y);return asc?x.localeCompare(y):y.localeCompare(x)});
 if($('oneper').checked){const seen=new Set();rows=rows.filter(r=>!seen.has(r.unit_id)&&seen.add(r.unit_id))}
 return rows}
function render(){
 const rows=filtered(),limit=+$('limit').value,shown=limit?rows.slice(0,limit):rows;
 $('count').textContent=`Showing ${shown.length.toLocaleString()} of ${rows.length.toLocaleString()} matching rows (${ROWS.length.toLocaleString()} embedded of __TOTAL__ fitted observations)`;
 document.querySelectorAll('th').forEach(th=>{th.classList.toggle('sorted',th.dataset.k===sortKey);th.classList.toggle('asc',th.dataset.k===sortKey&&asc)});
 const sign=v=>v>0?'pos':v<0?'neg':'';
 $('t').tBodies[0].innerHTML=shown.map(r=>{
  const ad=safe(r.advertisement_url),unit=safe(r.canonical_unit_url);
  const links=[ad?`<a href="${esc(ad)}" target="_blank" rel="noopener">ad</a>`:'',unit?`<a href="${esc(unit)}" target="_blank" rel="noopener">unit</a>`:''].filter(Boolean).join(' · ');
  return `<tr><td class="num">${r.rank}</td><td>${esc(r.building)}${r.current_capture?' <span class="tag">current</span>':''}</td><td>${esc(r.unit_label)}</td><td>${esc(String(r.period).slice(0,7))}</td>
  <td class="num">${num(r.bedrooms,0)}</td><td class="num">${num(r.bathrooms,1)}</td><td class="num">${r.square_feet==null?'':Math.round(r.square_feet)}</td><td class="num">${num(r.listed_floor,0)}</td>
  <td class="num">${money(r.asking_rent)}</td><td class="num">${money(r.fitted_rent_without_unit)}</td><td class="num ${sign(r.unit_deviation_percent)}"><b>${pct(r.unit_deviation_percent)}</b></td><td class="num ${sign(r.unit_deviation_dollars)}">${money(r.unit_deviation_dollars)}</td>
  <td class="num">${money(r.fitted_rent)}</td><td class="num ${sign(r.residual_percent)}">${pct(r.residual_percent)}</td><td class="num">${num(r.unit_effect_log,3)}</td><td class="num">${num(r.building_effect_log,3)}</td>
  <td class="num">${r.unit_observations}</td><td class="num">${r.residual_rank}</td><td>${r.source_review?`<span class="tag warn">${esc(r.source_review)}</span>`:''}</td><td>${links}</td><td class="desc">${esc(r.description)}</td></tr>`}).join('')}
document.querySelectorAll('th[data-k]').forEach(th=>th.addEventListener('click',()=>{const k=th.dataset.k;if(sortKey===k)asc=!asc;else{sortKey=k;asc=k==='rank'||k==='residual_rank'||k==='building'||k==='unit_label'||k==='period'}render()}));
['scope','dir','minpct','year','beds','search','oneper','limit'].forEach(id=>{$(id).addEventListener('input',render);$(id).addEventListener('change',render)});
render();
</script></body></html>
'''

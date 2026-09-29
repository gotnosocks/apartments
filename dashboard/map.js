// Rent map: what a typical apartment rents for in each building, by year and
// bedroom count. Static: reads map.json (`python -m rentfrontier.rentmap`,
// copied in by `rentfrontier.dashboard`); no dependencies. All data-derived
// text goes into the DOM through textContent. The small DOM helpers repeat
// app.js's so the two pages stay independent.

const SVGNS = 'http://www.w3.org/2000/svg';
const $ = (id) => document.getElementById(id);
const HIT = 24; // minimum hover target, px
// Five rent bands, light to dark (validated ordinal ramps, one per mode).
const BANDS = 5;
const RAMP = {
  light: ['#86b6ef', '#3987e5', '#256abf', '#184f95', '#0d366b'],
  dark: ['#184f95', '#256abf', '#3987e5', '#86b6ef', '#cde2fb'],
};
const BED_COLORS = ['var(--cat-1)', 'var(--cat-2)', 'var(--cat-3)', 'var(--cat-4)'];
const state = { data: null, bed: '1', year: 0, showBefore: false, playing: null, sort: { key: 'rent', dir: -1 } };

function svg(tag, attrs = {}, parent) {
  const n = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === undefined || v === null) continue;
    if (k === 'text') n.textContent = v;
    else n.setAttribute(k, v);
  }
  if (parent) parent.appendChild(n);
  return n;
}
function html(tag, attrs = {}, parent, text) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === undefined || v === null || v === false) continue;
    if (k === 'class') n.className = v;
    else n.setAttribute(k, v === true ? '' : v);
  }
  if (text !== undefined) n.textContent = text;
  if (parent) parent.appendChild(n);
  return n;
}
const usd = (x) => '$' + Math.round(x).toLocaleString('en-US');
const usdK = (x) => '$' + (x / 1000).toFixed(x < 10000 ? 1 : 0) + 'k';
const range = (lo, hi) => `${usd(lo)}–${usd(hi)}`;
const isDark = () => (document.documentElement.dataset.theme || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')) === 'dark';

// ---------- tooltip ----------
const tip = { el: null };
function showTip(evt, build) {
  const t = tip.el;
  t.replaceChildren();
  build(t);
  t.hidden = false;
  const pad = 14;
  const r = t.getBoundingClientRect();
  let x = (evt.clientX ?? 0) + pad, y = (evt.clientY ?? 0) + pad;
  if (x + r.width > window.innerWidth - 8) x = (evt.clientX ?? 0) - r.width - pad;
  if (y + r.height > window.innerHeight - 8) y = (evt.clientY ?? 0) - r.height - pad;
  t.style.left = `${Math.max(8, x)}px`;
  t.style.top = `${Math.max(8, y)}px`;
}
function hideTip() { tip.el.hidden = true; }
function tipRow(t, name, value) {
  const row = html('div', { class: 't-row' }, t);
  html('span', {}, row, name);
  html('span', {}, row, value);
}
function pointerPos(root, evt) {
  const r = root.getBoundingClientRect();
  const vb = root.viewBox.baseVal;
  return [((evt.clientX - r.left) / r.width) * vb.width, ((evt.clientY - r.top) / r.height) * vb.height];
}

// ---------- data ----------
const yearIndex = () => state.year;
const yearOf = (i) => state.data.years[i];
function rentOf(b, bedKey, yi) { return state.data.rent[bedKey][b][yi]; } // [p05, median, p95]
// Fixed bands per bedroom count: quintiles of the medians over every building-year
// where the building has listings, rounded to $50, so a band means the same in every year.
function bandBreaks(bedKey) {
  const d = state.data, vals = [];
  d.buildings.forEach((b, i) => d.years.forEach((y, yi) => { if (y >= b.first_year) vals.push(rentOf(i, bedKey, yi)[1]); }));
  vals.sort((a, b) => a - b);
  const q = (p) => vals[Math.min(vals.length - 1, Math.floor(p * vals.length))];
  return Array.from({ length: BANDS - 1 }, (_, k) => Math.round(q((k + 1) / BANDS) / 50) * 50);
}
const bandOf = (x, breaks) => breaks.filter((b) => x >= b).length;
const visible = (b, yi) => state.showBefore || yearOf(yi) >= b.first_year;

// ---------- controls ----------
function buildControls() {
  const d = state.data;
  const seg = $('beds-select');
  for (const b of d.bedrooms) {
    const lab = html('label', { class: 'chip' }, seg);
    const inp = html('input', { type: 'radio', name: 'beds', value: b.key, checked: b.key === state.bed }, lab);
    lab.appendChild(document.createTextNode(' ' + b.label));
    inp.addEventListener('change', () => { state.bed = b.key; render(); });
  }
  const r = $('year-range');
  r.max = d.years.length - 1;
  state.year = d.years.length - 1;
  r.value = state.year;
  r.addEventListener('input', () => { state.year = Number(r.value); render(); });
  const step = (k) => { state.year = Math.max(0, Math.min(d.years.length - 1, state.year + k)); r.value = state.year; render(); };
  $('year-prev').addEventListener('click', () => step(-1));
  $('year-next').addEventListener('click', () => step(1));
  $('year-play').addEventListener('click', () => {
    if (state.playing) { clearInterval(state.playing); state.playing = null; $('year-play').textContent = 'Play'; return; }
    if (state.year === d.years.length - 1) { state.year = 0; r.value = 0; render(); }
    $('year-play').textContent = 'Pause';
    state.playing = setInterval(() => {
      if (state.year >= d.years.length - 1) { clearInterval(state.playing); state.playing = null; $('year-play').textContent = 'Play'; return; }
      step(1);
    }, 900);
  });
  $('show-before').addEventListener('change', (e) => { state.showBefore = e.target.checked; render(); });
  for (const b of document.querySelectorAll('.table-toggle')) {
    b.addEventListener('click', () => {
      const t = $(`table-${b.dataset.target}`);
      t.hidden = !t.hidden;
      b.textContent = t.hidden ? 'Table view' : 'Chart view';
      $(`chart-${b.dataset.target}`).hidden = !t.hidden;
    });
  }
  const saved = localStorage.getItem('dashboard-theme');
  if (saved) document.documentElement.dataset.theme = saved;
  const btn = $('theme');
  const label = () => { btn.textContent = isDark() ? 'Light mode' : 'Dark mode'; };
  label();
  btn.addEventListener('click', () => {
    const next = isDark() ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    localStorage.setItem('dashboard-theme', next);
    label();
    render();
  });
}

// ---------- headline numbers ----------
function renderKpis() {
  const d = state.data, yi = yearIndex(), bedLabel = d.bedrooms.find((b) => b.key === state.bed).label;
  const [lo, mid, hi] = d.chelsea_average[state.bed][yi];
  const first = d.chelsea_average[state.bed][0][1];
  const shown = d.buildings.filter((b) => visible(b, yi)).length;
  const k = $('map-kpis');
  k.replaceChildren();
  const tile = (label, value, sub, hero) => {
    const t = html('div', { class: 'tile' + (hero ? ' hero' : '') }, k);
    html('div', { class: 'label' }, t, label);
    html('div', { class: 'value' }, t, value);
    if (sub) html('div', { class: 'sub' }, t, sub);
  };
  const partial = d.year_months[yi] < 12 ? ` (${d.year_months[yi]} months)` : '';
  tile(`Chelsea average, ${bedLabel.toLowerCase()}, ${yearOf(yi)}${partial}`, usd(mid), `90% interval ${range(lo, hi)} a month`, true);
  const ch = mid / first - 1;
  tile(`Since ${d.years[0]}`, `${ch >= 0 ? '+' : '−'}${Math.abs(100 * ch).toFixed(0)}%`, `from ${usd(first)} a month`);
  tile('Buildings on the map', shown.toLocaleString('en-US'), `of ${d.buildings.length.toLocaleString('en-US')} with listings in the fit`);
}

// ---------- map ----------
function renderMap() {
  const d = state.data, yi = yearIndex(), bed = state.bed;
  const breaks = bandBreaks(bed), ramp = RAMP[isDark() ? 'dark' : 'light'];
  const container = $('chart-map');
  container.replaceChildren();
  const pts = d.buildings.filter((b) => b.x !== null);
  const xs = pts.map((b) => b.x), ys = pts.map((b) => b.y);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const width = Math.max(320, container.clientWidth);
  const m = { left: 56, right: 70, top: 26, bottom: 30 };
  const scale = (width - m.left - m.right) / (x1 - x0);
  const height = Math.round((y1 - y0) * scale + m.top + m.bottom);
  const root = svg('svg', { viewBox: `0 0 ${width} ${height}`, width, height, role: 'img',
    'aria-label': `Map of typical ${bed === 'studio' ? 'studio' : bed + '-bedroom'} rents by building in ${yearOf(yi)}` }, container);
  const X = (x) => m.left + (x - x0) * scale, Y = (y) => m.top + (y1 - y) * scale;
  const g = svg('g', { class: 'grid' }, root);
  for (const a of d.grid.avenues) {
    svg('line', { x1: X(a.x), x2: X(a.x), y1: m.top - 8, y2: height - m.bottom + 8 }, g);
    svg('text', { x: X(a.x), y: height - 8, 'text-anchor': 'middle', text: a.label }, root);
  }
  for (const s of d.grid.streets) {
    svg('line', { x1: m.left - 8, x2: width - m.right + 8, y1: Y(s.y), y2: Y(s.y) }, g);
    svg('text', { x: width - m.right + 12, y: Y(s.y) + 4, text: s.label }, root);
  }
  svg('text', { class: 'axis-title', x: 16, y: (m.top + height - m.bottom) / 2, 'text-anchor': 'middle',
    transform: `rotate(-90 16 ${(m.top + height - m.bottom) / 2})`, text: '← Hudson River (west)' }, root);
  const marks = [];
  const layer = svg('g', {}, root);
  // Draw low bands first so the dearest buildings sit on top; hollow extrapolations under all.
  const order = d.buildings.map((b, i) => i).filter((i) => d.buildings[i].x !== null && visible(d.buildings[i], yi))
    .sort((a, b) => {
      const ea = yearOf(yi) < d.buildings[a].first_year, eb = yearOf(yi) < d.buildings[b].first_year;
      if (ea !== eb) return ea ? -1 : 1;
      return rentOf(a, bed, yi)[1] - rentOf(b, bed, yi)[1];
    });
  for (const i of order) {
    const b = d.buildings[i], v = rentOf(i, bed, yi), col = ramp[bandOf(v[1], breaks)];
    const extrap = yearOf(yi) < b.first_year;
    const node = svg('circle', { class: 'dot' + (extrap ? ' hollow' : ''), cx: X(b.x), cy: Y(b.y), r: 4.5,
      style: extrap ? `stroke:${col}` : `fill:${col}` }, layer);
    marks.push({ x: X(b.x), y: Y(b.y), i, node });
  }
  let lifted = null;
  root.addEventListener('pointermove', (evt) => {
    const [px, py] = pointerPos(root, evt);
    let best = null, bd = Infinity;
    for (const p of marks) { const dd = Math.hypot(p.x - px, p.y - py); if (dd < bd) { bd = dd; best = p; } }
    if (lifted) lifted.classList.remove('lift');
    if (!best || bd > HIT) { hideTip(); return; }
    lifted = best.node; lifted.classList.add('lift');
    showTip(evt, (t) => buildingTip(t, best.i, yi));
  });
  root.addEventListener('pointerleave', () => { hideTip(); if (lifted) lifted.classList.remove('lift'); });
  // Legend: the five bands.
  const lg = $('legend-map');
  lg.replaceChildren();
  const edges = [null, ...breaks, null];
  for (let k = 0; k < BANDS; k++) {
    const it = html('span', { class: 'item' }, lg);
    const sw = html('span', { class: 'swatch' }, it);
    sw.style.background = ramp[k];
    const lo = edges[k], hi = edges[k + 1];
    it.appendChild(document.createTextNode(lo === null ? `under ${usd(hi)}` : hi === null ? `${usd(lo)} and up` : `${usd(lo)}–${usd(hi)}`));
  }
  const ex = html('span', { class: 'item' }, lg);
  html('span', { class: 'swatch hollow' }, ex);
  ex.appendChild(document.createTextNode('before the building\'s first listing (extrapolated)'));
  renderMapTable(order, yi);
}
function buildingTip(t, i, yi) {
  const d = state.data, b = d.buildings[i], v = rentOf(i, state.bed, yi);
  html('div', { class: 't-value' }, t, `${usd(v[1])} a month`);
  html('div', { class: 't-name' }, t, b.label);
  tipRow(t, '90% interval', range(v[0], v[2]));
  tipRow(t, 'Chelsea average', usd(d.chelsea_average[state.bed][yi][1]));
  tipRow(t, 'Listings in the fit', `${b.fit_listings.toLocaleString('en-US')} (${b.first_year}–${b.last_year})`);
  if (yearOf(yi) < b.first_year) html('div', { class: 't-note' }, t, `No listings before ${b.first_year}: the model's extrapolation.`);
}
function renderMapTable(order, yi) {
  const d = state.data, bed = state.bed, wrap = $('table-map');
  wrap.replaceChildren();
  const rows = order.map((i) => ({ i, b: d.buildings[i], v: rentOf(i, bed, yi) }));
  const key = state.sort.key, dir = state.sort.dir;
  const val = { building: (r) => r.b.label, rent: (r) => r.v[1], listings: (r) => r.b.fit_listings, first: (r) => r.b.first_year };
  rows.sort((a, b) => { const x = val[key](a), y = val[key](b); return (x < y ? -1 : x > y ? 1 : 0) * dir; });
  const table = html('table', {}, wrap);
  const head = html('tr', {}, html('thead', {}, table));
  for (const [k, label, num] of [['building', 'Building', false], ['rent', 'Typical rent', true], [null, '90% interval', true],
    ['listings', 'Listings in the fit', true], ['first', 'Listed from', true]]) {
    const th = html('th', { class: num ? 'num' : undefined, scope: 'col' }, head);
    if (!k) { th.textContent = label; continue; }
    const btn = html('button', { type: 'button' }, th, label + (key === k ? (dir > 0 ? ' ▲' : ' ▼') : ''));
    btn.addEventListener('click', () => { state.sort = { key: k, dir: key === k ? -dir : (k === 'building' ? 1 : -1) }; renderMap(); });
  }
  const body = html('tbody', {}, table);
  for (const r of rows) {
    const tr = html('tr', {}, body);
    html('td', {}, tr, r.b.label);
    html('td', { class: 'num' }, tr, usd(r.v[1]));
    html('td', { class: 'num' }, tr, range(r.v[0], r.v[2]));
    html('td', { class: 'num' }, tr, r.b.fit_listings.toLocaleString('en-US'));
    html('td', { class: 'num' }, tr, String(r.b.first_year));
  }
}

// ---------- Chelsea average over time ----------
function renderTrend() {
  const d = state.data, yi = yearIndex();
  const container = $('chart-trend');
  container.replaceChildren();
  const width = Math.max(320, container.clientWidth), height = 300;
  const m = { left: 64, right: 110, top: 16, bottom: 34 };
  const root = svg('svg', { viewBox: `0 0 ${width} ${height}`, width, height, role: 'img', 'aria-label': 'Chelsea average typical rent by bedrooms over time' }, container);
  const all = d.bedrooms.flatMap((b) => d.chelsea_average[b.key].flat());
  const lo = 0, hi = Math.max(...all) * 1.05;
  const X = (i) => m.left + (i / (d.years.length - 1)) * (width - m.left - m.right);
  const Y = (v) => height - m.bottom - ((v - lo) / (hi - lo)) * (height - m.top - m.bottom);
  const step = hi > 12000 ? 2000 : 1000;
  const g = svg('g', { class: 'grid' }, root);
  for (let v = 0; v <= hi; v += step) {
    svg('line', { x1: m.left, x2: width - m.right, y1: Y(v), y2: Y(v) }, g);
    svg('text', { x: m.left - 8, y: Y(v) + 4, 'text-anchor': 'end', text: usdK(v) }, root);
  }
  svg('line', { class: 'baseline', x1: m.left, x2: width - m.right, y1: Y(0), y2: Y(0) }, root);
  d.years.forEach((y, i) => { if (i % 2 === 0 || i === d.years.length - 1) svg('text', { x: X(i), y: height - m.bottom + 17, 'text-anchor': 'middle', text: String(y) }, root); });
  // The chosen bedroom count's 90% band, under the lines.
  const sel = d.chelsea_average[state.bed];
  const band = sel.map((v, i) => `${X(i)},${Y(v[2])}`).concat(sel.slice().reverse().map((v, j) => `${X(sel.length - 1 - j)},${Y(v[0])}`));
  svg('polygon', { class: 'frontier-wash', points: band.join(' ') }, root);
  svg('line', { class: 'cursor', x1: X(yi), x2: X(yi), y1: m.top, y2: height - m.bottom }, root);
  const lg = $('legend-trend');
  lg.replaceChildren();
  d.bedrooms.forEach((b, k) => {
    const series = d.chelsea_average[b.key];
    const chosen = b.key === state.bed;
    svg('polyline', { class: 'series-line', points: series.map((v, i) => `${X(i)},${Y(v[1])}`).join(' '),
      style: `stroke:${BED_COLORS[k]};stroke-width:${chosen ? 2.5 : 2}` }, root);
    svg('text', { class: 'label', x: width - m.right + 8, y: Y(series[series.length - 1][1]) + 4, text: b.label }, root);
    const it = html('span', { class: 'item' }, lg);
    const key = html('span', { class: 'rect' }, it);
    key.style.background = BED_COLORS[k];
    it.appendChild(document.createTextNode(b.label));
  });
  const hl = svg('line', { class: 'hover-line', x1: 0, x2: 0, y1: m.top, y2: height - m.bottom, visibility: 'hidden' }, root);
  root.addEventListener('pointermove', (evt) => {
    const [px] = pointerPos(root, evt);
    const i = Math.max(0, Math.min(d.years.length - 1, Math.round(((px - m.left) / (width - m.left - m.right)) * (d.years.length - 1))));
    hl.setAttribute('x1', X(i)); hl.setAttribute('x2', X(i)); hl.setAttribute('visibility', 'visible');
    showTip(evt, (t) => {
      html('div', { class: 't-value' }, t, String(d.years[i]) + (d.year_months[i] < 12 ? ` (${d.year_months[i]} months)` : ''));
      d.bedrooms.forEach((b) => { const v = d.chelsea_average[b.key][i]; tipRow(t, b.label, `${usd(v[1])} (${range(v[0], v[2])})`); });
    });
  });
  root.addEventListener('pointerleave', () => { hideTip(); hl.setAttribute('visibility', 'hidden'); });
  root.addEventListener('click', (evt) => {
    const [px] = pointerPos(root, evt);
    state.year = Math.max(0, Math.min(d.years.length - 1, Math.round(((px - m.left) / (width - m.left - m.right)) * (d.years.length - 1))));
    $('year-range').value = state.year;
    render();
  });
  // Table view.
  const wrap = $('table-trend');
  wrap.replaceChildren();
  const table = html('table', {}, wrap);
  const head = html('tr', {}, html('thead', {}, table));
  html('th', { scope: 'col' }, head, 'Year');
  for (const b of d.bedrooms) html('th', { class: 'num', scope: 'col' }, head, `${b.label} (90% interval)`);
  const body = html('tbody', {}, table);
  d.years.forEach((y, i) => {
    const tr = html('tr', {}, body);
    html('td', {}, tr, String(y) + (d.year_months[i] < 12 ? ` (${d.year_months[i]} months)` : ''));
    for (const b of d.bedrooms) { const v = d.chelsea_average[b.key][i]; html('td', { class: 'num' }, tr, `${usd(v[1])} (${range(v[0], v[2])})`); }
  });
}

function render() {
  $('year-label').textContent = String(yearOf(yearIndex()));
  const bedLabel = state.data.bedrooms.find((b) => b.key === state.bed).label;
  $('map-title').textContent = `Typical rent by building: ${bedLabel.toLowerCase()}, ${yearOf(yearIndex())}`;
  renderKpis();
  renderMap();
  renderTrend();
}

async function main() {
  tip.el = $('tooltip');
  let d;
  try {
    const r = await fetch('map.json', { cache: 'no-cache' });
    if (!r.ok) throw new Error(r.status);
    d = await r.json();
  } catch {
    $('map-kpis').textContent = 'No rent map for the selected model yet (python -m rentfrontier.rentmap <run>).';
    return;
  }
  state.data = d;
  $('map-definition').textContent = d.definition;
  $('map-meta').textContent = `${d.model} · ${d.feature_set} · ${d.draws.toLocaleString('en-US')} draws · made ${d.created_at.slice(0, 10)}`;
  const foot = $('map-foot');
  html('p', {}, foot, `Run ${d.run} (commit ${d.run_commit.slice(0, 7)}); map at commit ${d.commit.slice(0, 7)}.`);
  html('p', {}, foot, 'Typical rents are the model\'s, not listings\' asks: a building with few listings leans on Chelsea and on buildings like it. '
    + 'Intervals are the model\'s uncertainty about the typical ask, not the spread of individual asks.');
  buildControls();
  render();
  let resize;
  window.addEventListener('resize', () => { clearTimeout(resize); resize = setTimeout(render, 150); });
}
main();

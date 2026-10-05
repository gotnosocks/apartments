// Rent map: what a typical apartment rents for in each building, by year and
// bedroom count. Reads the published build's map.json (`rentfrontier.rentmap`
// for the served run, bundled by `apartments.site build`) from the URL in
// #rent-map's data-src; no dependencies. All data-derived text goes into the
// DOM through textContent; styles go through the CSS object model, so the
// site's CSP (no inline style attributes) holds.

const SVGNS = 'http://www.w3.org/2000/svg';
const $ = (id) => document.getElementById(id);
const HIT = 24; // minimum hover target, px
// Diverging classes of a building's premium over the area's median building that
// year (blue cheaper, red dearer, gray within 5%). Each arm is a validated
// ordinal ramp: on light, darker away from the middle; on dark, lighter.
const BREAKS = [-0.30, -0.15, -0.05, 0.05, 0.15, 0.30];
const CLASS_LABELS = ['30% or more below', '15–30% below', '5–15% below', 'within 5%', '5–15% above', '15–30% above', '30% or more above'];
const RAMP = {
  light: ['#184f95', '#3987e5', '#86b6ef', 'var(--map-neutral)', '#ea9a93', '#d75853', '#892b2a'],
  dark: ['#86b6ef', '#3987e5', '#184f95', 'var(--map-neutral)', '#892b2a', '#d75853', '#ea9a93'],
};
const BED_COLORS = ['var(--s1)', 'var(--s2)', 'var(--s3)', 'var(--s4)'];
const state = { data: null, area: null, base: 0, bed: '1', year: 0, showBefore: false, playing: null, sort: { key: 'rent', dir: -1 } };

function svg(tag, attrs = {}, parent) {
  const n = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === undefined || v === null) continue;
    if (k === 'text') n.textContent = v;
    else if (k === 'style') n.style.cssText = v;
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
const usdK = (x) => (x === 0 ? '$0' : `$${x / 1000}k`);
const pctText = (p) => (Math.abs(p) < 0.005 ? 'at' : `${p > 0 ? '+' : '−'}${Math.abs(100 * p).toFixed(0)}%`);
const range = (lo, hi) => `${usd(lo)}–${usd(hi)}`;
const isDark = () => matchMedia('(prefers-color-scheme: dark)').matches;

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
// The median building's series for a bedroom key: of the chosen neighbourhood
// (map.json's median_by_area, when it has one), else of the whole area.
const medianSeries = (bedKey) => {
  const d = state.data, byArea = state.area && d.median_by_area && d.median_by_area[state.area];
  return byArea ? byArea[bedKey] : d.median[bedKey];
};
const median = (bedKey, yi) => medianSeries(bedKey)[yi]; // [p05, median, p95]
const areaName = () => state.area || state.data.area;
const premium = (i, bedKey, yi) => rentOf(i, bedKey, yi)[1] / median(bedKey, yi)[1] - 1;
const classOf = (p) => BREAKS.filter((b) => p >= b).length;
// Years outside a building's listings in the fit are the model's extrapolation.
const extrapolated = (b, yi) => yearOf(yi) < b.first_year || yearOf(yi) > b.last_year;
const inArea = (b) => !state.area || b.neighbourhood === state.area;
const visible = (b, yi) => inArea(b) && (state.showBefore || !extrapolated(b, yi));

// ---------- controls ----------
function buildControls() {
  const d = state.data;
  const areas = Object.keys(d.median_by_area || {}).sort();
  if (areas.length > 1 && d.buildings.some((b) => b.neighbourhood)) {
    const box = $('area-select');
    box.hidden = false;
    for (const [value, label] of [['', `All of ${d.area}`], ...areas.map((a) => [a, a])]) {
      const lab = html('label', { class: 'chip' }, box);
      const inp = html('input', { type: 'radio', name: 'area', value, checked: value === '' }, lab);
      lab.appendChild(document.createTextNode(' ' + label));
      inp.addEventListener('change', () => { state.area = value || null; view.zoom = 1; view.cx = null; view.cy = null; render(); });
    }
  }
  const seg = $('beds-select');
  for (const b of d.bedrooms) {
    const lab = html('label', { class: 'chip' }, seg);
    const inp = html('input', { type: 'radio', name: 'beds', value: b.key, checked: b.key === state.bed }, lab);
    lab.appendChild(document.createTextNode(' ' + b.label));
    inp.addEventListener('change', () => { state.bed = b.key; render(); });
  }
  const base = $('base-year');
  d.years.forEach((y, i) => html('option', { value: String(i), selected: i === state.base }, base, String(y)));
  base.addEventListener('change', () => { state.base = Number(base.value); render(); });
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
  initMapEvents();
  $('zoom-in').addEventListener('click', () => zoomBy(2));
  $('zoom-out').addEventListener('click', () => zoomBy(0.5));
  $('zoom-reset').addEventListener('click', () => { view.zoom = 1; view.cx = null; view.cy = null; renderMap(); });
  for (const b of document.querySelectorAll('.table-toggle')) {
    b.addEventListener('click', () => {
      const t = $(`table-${b.dataset.target}`);
      t.hidden = !t.hidden;
      b.textContent = t.hidden ? 'Table view' : 'Chart view';
      $(`chart-${b.dataset.target}`).hidden = !t.hidden;
      // A chart rebuilt while hidden was sized to the fallback width: redraw it.
      if (t.hidden) render();
    });
  }
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', render);
}

// ---------- headline numbers ----------
function renderKpis() {
  const d = state.data, yi = yearIndex(), bedLabel = d.bedrooms.find((b) => b.key === state.bed).label;
  const [lo, mid, hi] = median(state.bed, yi);
  const first = median(state.bed, state.base)[1];
  const shown = d.buildings.filter((b) => visible(b, yi)).length;
  const total = d.buildings.filter(inArea).length;
  const k = $('map-kpis');
  k.replaceChildren();
  const tile = (label, value, sub, hero) => {
    const t = html('div', { class: 'tile' + (hero ? ' hero' : '') }, k);
    html('div', { class: 'label' }, t, label);
    html('div', { class: 'value' }, t, value);
    if (sub) html('div', { class: 'sub' }, t, sub);
  };
  const partial = d.year_months[yi] < 12 ? ` (${d.year_months[yi]} months)` : '';
  tile(`Median building ${state.area ? 'in' : 'across'} ${areaName()}, ${bedLabel.toLowerCase()}, ${yearOf(yi)}${partial}`, usd(mid),
    `90% interval ${range(lo, hi)} a month: how sure the model is of this typical rent, not the range of asks. `
    + `A typical apartment of that size has the average baths, size and features of its bedroom count.`, true);
  const ch = mid / first - 1;
  tile(`Since ${d.years[state.base]}`, `${ch >= 0 ? '+' : '−'}${Math.abs(100 * ch).toFixed(0)}%`, `from ${usd(first)} a month`);
  tile('Buildings on the map', shown.toLocaleString('en-US'), `of ${total.toLocaleString('en-US')} with listings in the fit${state.showBefore ? '' : `; shown where their listings span ${yearOf(yi)}`}`);
}

// ---------- map ----------
// The view: world centre (grid metres) and zoom over the fit-to-window scale.
const view = { cx: null, cy: null, zoom: 1 };
const FT = 0.3048; // metres per foot
// The mapped area: the basemap's extent, or the buildings' own (older bundles).
function mapExtent() {
  const d = state.data;
  if (d.basemap) return d.basemap.extent;
  const xs = d.buildings.filter((b) => b.x !== null).map((b) => b.x), ys = d.buildings.filter((b) => b.y !== null).map((b) => b.y);
  return [Math.min(...xs) - 120, Math.max(...xs) + 120, Math.min(...ys) - 120, Math.max(...ys) + 120];
}
function mapFrame(container) {
  const [ex0, ex1, ey0, ey1] = mapExtent(), aspect = (ex1 - ex0) / (ey1 - ey0);
  // The frame has the mapped area's proportions (no water painted over land), as
  // large as fits the card's width and the window below where the map starts in
  // the page (its document position, so it does not depend on the scroll).
  const top = container.getBoundingClientRect().top + window.scrollY;
  const tall = Math.max(280, window.innerHeight - top - 24);
  const width = Math.round(Math.min(Math.max(320, container.clientWidth), tall * aspect));
  const height = Math.round(width / aspect);
  const k = (width / (ex1 - ex0)) * view.zoom;
  // Keep the view inside the mapped area.
  const hw = width / 2 / k, hh = height / 2 / k;
  view.cx = Math.min(ex1 - hw, Math.max(ex0 + hw, view.cx ?? (ex0 + ex1) / 2));
  view.cy = Math.min(ey1 - hh, Math.max(ey0 + hh, view.cy ?? (ey0 + ey1) / 2));
  const X = (x) => width / 2 + (x - view.cx) * k, Y = (y) => height / 2 - (y - view.cy) * k;
  return { width, height, k, X, Y };
}
const pathOf = (pts, X, Y, close) => pts.map((p, i) => `${i ? 'L' : 'M'}${X(p[0]).toFixed(1)},${Y(p[1]).toFixed(1)}`).join('') + (close ? 'Z' : '');
function drawBasemap(root, f) {
  const b = state.data.basemap, { X, Y, k } = f;
  if (!b) return;
  svg('rect', { class: 'water', x: 0, y: 0, width: f.width, height: f.height }, root);
  for (const land of b.land) svg('path', { class: 'land', 'fill-rule': 'evenodd', d: land.rings.map((r) => pathOf(r, X, Y, true)).join('') }, root);
  for (const park of b.parks) {
    const n = svg('path', { class: 'park', d: park.rings.map((r) => pathOf(r, X, Y, true)).join('') }, root);
    svg('title', { text: park.name || 'Park' }, n);
  }
  for (const p of b.paths) svg('path', { class: 'path', d: pathOf(p.points, X, Y, false) }, root);
  // Streets at their recorded width (feet), never thinner than a hairline.
  for (const s of b.streets) {
    const w = Math.min(60, Math.max(0.8, (s.width_ft || 30) * FT * k));
    svg('path', { class: 'street', 'stroke-width': w.toFixed(1), d: pathOf(s.points, X, Y, false) }, root);
  }
  const g = state.data.grid;
  for (const a of g.avenues) {
    const x = X(a.x);
    if (x > 20 && x < f.width - 20) svg('text', { class: 'map-label', x, y: f.height - 6, 'text-anchor': 'middle', text: a.label }, root);
  }
  for (const s of g.streets) {
    const y = Y(s.y);
    if (y > 12 && y < f.height - 20) svg('text', { class: 'map-label', x: f.width - 6, y: y + 4, 'text-anchor': 'end', text: s.label }, root);
  }
  svg('text', { class: 'water-label', x: 14, y: f.height / 2, transform: `rotate(-90 14 ${f.height / 2})`, 'text-anchor': 'middle', text: 'Hudson River' }, root);
}
function renderMap() {
  const d = state.data, yi = yearIndex(), bed = state.bed;
  const ramp = RAMP[isDark() ? 'dark' : 'light'];
  // Legend: the seven classes, cheapest to dearest.
  const lg = $('legend-map');
  lg.replaceChildren();
  CLASS_LABELS.forEach((label, k) => {
    const it = html('span', { class: 'item' }, lg);
    const sw = html('span', { class: 'swatch' }, it);
    sw.style.background = ramp[k];
    it.appendChild(document.createTextNode(label));
  });
  const ex = html('span', { class: 'item' }, lg);
  html('span', { class: 'swatch hollow' }, ex);
  ex.appendChild(document.createTextNode('outside the years of the building\'s listings (extrapolated)'));
  const container = $('chart-map');
  container.replaceChildren();
  const f = mapFrame(container), { X, Y } = f;
  const root = svg('svg', { viewBox: `0 0 ${f.width} ${f.height}`, width: f.width, height: f.height, role: 'img',
    'aria-label': `Map of typical ${bed === 'studio' ? 'studio' : bed + '-bedroom'} rents by building in ${yearOf(yi)}` }, container);
  drawBasemap(root, f);
  const marks = [];
  const layer = svg('g', {}, root);
  // Draw near-median buildings first so strong premiums and discounts sit on top;
  // hollow extrapolations under all.
  const order = d.buildings.map((b, i) => i).filter((i) => d.buildings[i].x !== null && visible(d.buildings[i], yi))
    .sort((a, b) => {
      const ea = extrapolated(d.buildings[a], yi), eb = extrapolated(d.buildings[b], yi);
      if (ea !== eb) return ea ? -1 : 1;
      return Math.abs(premium(a, bed, yi)) - Math.abs(premium(b, bed, yi));
    });
  const r = Math.min(7, 4.5 * Math.sqrt(view.zoom));
  for (const i of order) {
    const b = d.buildings[i], col = ramp[classOf(premium(i, bed, yi))];
    const cx = X(b.x), cy = Y(b.y);
    if (cx < -10 || cx > f.width + 10 || cy < -10 || cy > f.height + 10) continue;
    const extrap = extrapolated(b, yi);
    const node = svg('circle', { class: 'dot' + (extrap ? ' hollow' : ''), cx, cy, r,
      style: extrap ? `stroke:${col}` : `fill:${col}` }, layer);
    marks.push({ x: cx, y: cy, i, node });
  }
  mapState.f = f; mapState.marks = marks; mapState.yi = yi;
  renderMapTable(order, yi);
}
// Pointer handling lives on the container, which survives re-renders (a drag
// re-renders every frame): hover tooltips, drag to pan, double click to zoom.
const mapState = { f: null, marks: [], yi: 0, drag: null, lifted: null };
function initMapEvents() {
  const c = $('chart-map');
  const pos = (evt) => {
    const r = c.querySelector('svg').getBoundingClientRect();
    return [((evt.clientX - r.left) / r.width) * mapState.f.width, ((evt.clientY - r.top) / r.height) * mapState.f.height];
  };
  c.addEventListener('pointermove', (evt) => {
    if (!mapState.f) return;
    const [px, py] = pos(evt), drag = mapState.drag;
    if (drag) {
      if (Math.hypot(px - drag.px, py - drag.py) > 4) mapState.moved = true;
      view.cx = drag.cx - (px - drag.px) / mapState.f.k; view.cy = drag.cy + (py - drag.py) / mapState.f.k;
      if (!drag.frame) drag.frame = requestAnimationFrame(() => { drag.frame = null; renderMap(); });
      return;
    }
    let best = null, bd = Infinity;
    for (const p of mapState.marks) { const dd = Math.hypot(p.x - px, p.y - py); if (dd < bd) { bd = dd; best = p; } }
    if (mapState.lifted) mapState.lifted.classList.remove('lift');
    if (!best || bd > HIT) { hideTip(); return; }
    mapState.lifted = best.node; best.node.classList.add('lift');
    showTip(evt, (t) => buildingTip(t, best.i, mapState.yi));
  });
  c.addEventListener('pointerdown', (evt) => {
    mapState.moved = false; // a new press: no drag yet
    if (!mapState.f || view.zoom === 1) return; // nothing to pan at the whole-map view
    const [px, py] = pos(evt);
    mapState.drag = { px, py, cx: view.cx, cy: view.cy, frame: null };
    c.setPointerCapture(evt.pointerId); c.classList.add('dragging'); hideTip();
  });
  const end = () => { mapState.drag = null; c.classList.remove('dragging'); };
  c.addEventListener('pointerup', end);
  c.addEventListener('pointercancel', end);
  c.addEventListener('pointerleave', () => { hideTip(); if (mapState.lifted) mapState.lifted.classList.remove('lift'); });
  // A single click (not the end of a drag, not part of a double click, which
  // zooms) on a building opens its page, after a short wait for a second click.
  c.addEventListener('click', (evt) => {
    if (!mapState.f || mapState.moved) return;
    clearTimeout(mapState.open);
    if (evt.detail > 1) return;
    const [px, py] = pos(evt);
    let best = null, bd = Infinity;
    for (const p of mapState.marks) { const dd = Math.hypot(p.x - px, p.y - py); if (dd < bd) { bd = dd; best = p; } }
    if (!best || bd > HIT) return;
    const url = buildingUrl(state.data.buildings[best.i].id);
    mapState.open = setTimeout(() => { window.location.href = url; }, 300);
  });
  c.addEventListener('dblclick', (evt) => {
    clearTimeout(mapState.open);
    if (!mapState.f) return;
    const [px, py] = pos(evt);
    view.cx += (px - mapState.f.width / 2) / mapState.f.k; view.cy -= (py - mapState.f.height / 2) / mapState.f.k;
    zoomBy(2);
  });
}
function buildingUrl(id) { return '/buildings/' + encodeURIComponent(id); }
function zoomBy(factor) {
  view.zoom = Math.max(1, Math.min(8, view.zoom * factor));
  if (view.zoom === 1) { view.cx = null; view.cy = null; }
  renderMap();
}
function buildingTip(t, i, yi) {
  const d = state.data, b = d.buildings[i], v = rentOf(i, state.bed, yi);
  html('div', { class: 't-value' }, t, `${usd(v[1])} a month`);
  html('div', { class: 't-name' }, t, b.label);
  tipRow(t, '90% interval', range(v[0], v[2]));
  tipRow(t, 'Against the median building', `${pctText(premium(i, state.bed, yi))} (${usd(median(state.bed, yi)[1])})`);
  tipRow(t, 'Listings in the fit', `${b.fit_listings.toLocaleString('en-US')} (${b.first_year}–${b.last_year})`);
  if (extrapolated(b, yi)) html('div', { class: 't-note' }, t, `Listed only ${b.first_year}–${b.last_year}: the model's extrapolation.`);
}
function renderMapTable(order, yi) {
  const d = state.data, bed = state.bed, wrap = $('table-map');
  wrap.replaceChildren();
  const rows = order.map((i) => ({ i, b: d.buildings[i], v: rentOf(i, bed, yi) }));
  const key = state.sort.key, dir = state.sort.dir;
  const val = { building: (r) => r.b.label, rent: (r) => r.v[1], premium: (r) => premium(r.i, bed, yi), listings: (r) => r.b.fit_listings, first: (r) => r.b.first_year };
  rows.sort((a, b) => { const x = val[key](a), y = val[key](b); return (x < y ? -1 : x > y ? 1 : 0) * dir; });
  const table = html('table', {}, wrap);
  const head = html('tr', {}, html('thead', {}, table));
  for (const [k, label, num] of [['building', 'Building', false], ['rent', 'Typical rent', true], [null, '90% interval', true],
    ['premium', 'Against the median building', true],
    ['listings', 'Listings in the fit', true], ['first', 'Listed from', true]]) {
    const th = html('th', { class: num ? 'num' : undefined, scope: 'col' }, head);
    if (!k) { th.textContent = label; continue; }
    const btn = html('button', { type: 'button' }, th, label + (key === k ? (dir > 0 ? ' ▲' : ' ▼') : ''));
    btn.addEventListener('click', () => { state.sort = { key: k, dir: key === k ? -dir : (k === 'building' ? 1 : -1) }; renderMap(); });
  }
  const body = html('tbody', {}, table);
  for (const r of rows) {
    const tr = html('tr', {}, body);
    html('a', { href: buildingUrl(r.b.id) }, html('td', {}, tr), r.b.label);
    html('td', { class: 'num' }, tr, usd(r.v[1]));
    html('td', { class: 'num' }, tr, range(r.v[0], r.v[2]));
    html('td', { class: 'num' }, tr, pctText(premium(r.i, bed, yi)));
    html('td', { class: 'num' }, tr, r.b.fit_listings.toLocaleString('en-US'));
    html('td', { class: 'num' }, tr, String(r.b.first_year));
  }
}

// ---------- The area's median building over time ----------
function renderTrend() {
  const d = state.data, yi = yearIndex();
  const container = $('chart-trend');
  container.replaceChildren();
  const width = Math.max(320, container.clientWidth), height = 300;
  const m = { left: 64, right: 110, top: 16, bottom: 34 };
  const root = svg('svg', { viewBox: `0 0 ${width} ${height}`, width, height, role: 'img', 'aria-label': `Typical rent of the median building ${state.area ? 'in' : 'across'} ${areaName()}, by bedrooms over time` }, container);
  const all = d.bedrooms.flatMap((b) => medianSeries(b.key).flat());
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
  const sel = medianSeries(state.bed);
  const band = sel.map((v, i) => `${X(i)},${Y(v[2])}`).concat(sel.slice().reverse().map((v, j) => `${X(sel.length - 1 - j)},${Y(v[0])}`));
  svg('polygon', { class: 'frontier-wash', points: band.join(' ') }, root);
  svg('line', { class: 'cursor', x1: X(yi), x2: X(yi), y1: m.top, y2: height - m.bottom }, root);
  const lg = $('legend-trend');
  lg.replaceChildren();
  d.bedrooms.forEach((b, k) => {
    const series = medianSeries(b.key);
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
      d.bedrooms.forEach((b) => { const v = medianSeries(b.key)[i]; tipRow(t, b.label, `${usd(v[1])} (${range(v[0], v[2])})`); });
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
    for (const b of d.bedrooms) { const v = medianSeries(b.key)[i]; html('td', { class: 'num' }, tr, `${usd(v[1])} (${range(v[0], v[2])})`); }
  });
}

function render() {
  $('year-label').textContent = String(yearOf(yearIndex()));
  const bedLabel = state.data.bedrooms.find((b) => b.key === state.bed).label;
  $('map-title').textContent = `Typical rent by building ${state.area ? 'in' : 'across'} ${areaName()}: ${bedLabel.toLowerCase()}, ${yearOf(yearIndex())}`;
  $('area-caveat').hidden = !state.area;
  $('trend-title').textContent = `The median building ${state.area ? 'in' : 'across'} ${areaName()} by bedrooms over time`;
  renderKpis();
  renderMap();
  renderTrend();
}

async function main() {
  tip.el = $('tooltip');
  let d;
  try {
    const r = await fetch($('rent-map').dataset.src, { cache: 'no-cache' });
    if (!r.ok) throw new Error(r.status);
    d = await r.json();
  } catch {
    $('map-kpis').textContent = 'No rent map for the served model yet.';
    return;
  }
  // Maps from before rentfrontier named the area carry chelsea_median and no
  // area: the site's own name for its area stands in.
  d.median = d.median || d.chelsea_median;
  d.area = d.area || $('rent-map').dataset.area || 'Chelsea';
  state.data = d;
  $('map-definition').textContent = d.definition;
  $('map-meta').textContent = `${d.model} · ${d.feature_set} · ${d.draws.toLocaleString('en-US')} draws · made ${d.created_at.slice(0, 10)}`;
  const foot = $('map-foot');
  html('p', {}, foot, `Run ${d.run} (commit ${d.run_commit.slice(0, 7)}); map at commit ${d.commit.slice(0, 7)}.`);
  html('p', {}, foot, `Typical rents are the model's, not listings' asks: a building with few listings leans on the whole area (${d.area}) and on buildings like it. `
    + 'Intervals are the model\'s uncertainty about the typical ask, not the spread of individual asks.');
  buildControls();
  render();
  let resize;
  window.addEventListener('resize', () => { clearTimeout(resize); resize = setTimeout(render, 150); });
}
main();

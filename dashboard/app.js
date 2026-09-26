// Research-progress dashboard. Static: reads data.json written by
// `python -m rentfrontier.dashboard`; no dependencies. All data-derived text
// goes into the DOM through textContent.

const SVGNS = 'http://www.w3.org/2000/svg';
const $ = (id) => document.getElementById(id);
const LINES = {
  frontier: { label: 'Custom Gibbs (JAX, deprecated)', short: 'Gibbs (deprecated)', color: 'var(--series-1)' },
  pymc: { label: 'PyMC (NUTS)', short: 'PyMC', color: 'var(--series-2)' },
  numpyro: { label: 'NumPyro (NUTS)', short: 'NumPyro', color: 'var(--series-3)' },
};
const HIT = 24; // minimum hover target, px
// The area of interest: fits of at most 15 minutes (Ben, 2026-09-25).
const FIT_WINDOW = 15 * 60;
// Primary score: PSIS-LOO dELPD vs the baseline, with its combined error.
const score = (e) => (e.psis ? e.psis.delta : null);
const scoreErr = (e) => (e.psis ? Math.hypot(e.psis.delta_se, e.psis.delta_mcse) : null);
const heldout = (e) => e.splits.rows?.delta ?? null;
// The frontier is per hardware class; snapshots carry one record per class.
const EMPTY = { best: null, best_delta: null, frontier: [], entries: 0 };
// Per-class board state in a snapshot (frontier and best are per hardware class).
const cls = (snap, c) => (snap.by_class && snap.by_class[c]) || EMPTY;
// Short hardware names for labels: "RTX 2060 SUPER", "CPU", "Modal H100".
const hwShort = (c) => c.replace(/^thelio /, '').replace(/ \(.*\)$/, '');
// One dash pattern per selected class, for its frontier and best lines.
const DASHES = ['', '7 4', '2 3', '10 3 2 3', '1 5'];
const dashOf = (c) => DASHES[Math.max(0, state.hws.indexOf(c)) % DASHES.length];

const state = {
  data: null, idx: 0, showFailed: true, showSE: true, fullRange: false,
  lines: { frontier: true, pymc: true, numpyro: true }, sort: { key: 'psis', dir: -1 }, playing: null, hw: null,
};

// ---------- DOM helpers ----------
function svg(tag, attrs = {}, parent) {
  const n = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === undefined || v === null) continue;
    if (k === 'style') n.setAttribute('style', v);
    else if (k === 'text') n.textContent = v;
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
    else if (k === 'style') n.setAttribute('style', v);
    else n.setAttribute(k, v === true ? '' : v);
  }
  if (text !== undefined) n.textContent = text;
  if (parent) parent.appendChild(n);
  return n;
}

// ---------- formatting ----------
let fmtWhen, fmtDay, fmtHour;
function fmtDelta(x, digits = 1) {
  if (x === null || x === undefined || Number.isNaN(x)) return '—';
  const s = Math.abs(x).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
  return (x > 0 ? '+' : x < 0 ? '−' : '') + s;
}
function fmtSE(x) { return x === null || x === undefined ? '' : '± ' + x.toFixed(1); }
function fmtDur(s) {
  if (s === null || s === undefined) return '—';
  if (s < 90) return `${Math.round(s)} s`;
  if (s < 90 * 60) return `${(s / 60).toFixed(s < 600 ? 1 : 0)} min`;
  return `${(s / 3600).toFixed(1)} h`;
}
function entryLabel(e) {
  if (/^L\d/.test(e.design)) return `${e.design} · ${LINES[e.line]?.short || e.line}`; // ladder rungs
  return e.line === 'pymc' ? e.design.replace(/^nuts-/, 'PyMC ') : `${e.design} · ${e.feature_set}`;
}
function drawsText(e) {
  return e.chains && e.draws ? `${e.chains} × ${e.draws.toLocaleString('en-US')}` : e.line === 'pymc' ? '4 × 1,000' : '—';
}

// ---------- scales ----------
function linear([d0, d1], [r0, r1]) {
  const f = (v) => r0 + ((v - d0) / (d1 - d0)) * (r1 - r0);
  f.invert = (p) => d0 + ((p - r0) / (r1 - r0)) * (d1 - d0);
  f.domain = [d0, d1];
  return f;
}
function logScale([d0, d1], [r0, r1]) {
  const l0 = Math.log(d0), l1 = Math.log(d1);
  const f = (v) => r0 + ((Math.log(v) - l0) / (l1 - l0)) * (r1 - r0);
  f.invert = (p) => Math.exp(l0 + ((p - r0) / (r1 - r0)) * (l1 - l0));
  f.domain = [d0, d1];
  return f;
}
function niceTicks(lo, hi, count = 6) {
  const raw = (hi - lo) / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) || 10 * mag;
  const out = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(Math.round(v * 1e6) / 1e6);
  return out;
}
const DURATION_TICKS = [10, 30, 60, 120, 300, 600, 1200, 1800, 3600, 7200, 3 * 3600, 6 * 3600, 12 * 3600, 24 * 3600];
function durationTicks([d0, d1]) { return DURATION_TICKS.filter((v) => v >= d0 && v <= d1); }
function fmtDurTick(s) { return s < 60 ? `${s} s` : s < 3600 ? `${s / 60} min` : `${s / 3600} h`; }
function nyHour(t) { return Number(fmtHour.format(t)) % 24; }
function timeTicks([t0, t1], width) {
  const hours = (t1 - t0) / 3.6e6;
  const step = [1, 2, 3, 6, 12, 24].find((s) => hours / s <= Math.max(4, width / 90)) || 24;
  const out = [];
  for (let t = Math.ceil(t0 / 3.6e6) * 3.6e6; t <= t1; t += 3.6e6) {
    if (nyHour(t) % step === 0) out.push(t);
  }
  return out;
}
function timeTickLabel(t) {
  return nyHour(t) === 0 ? fmtDay.format(t) : fmtWhen.format(t).split(', ').pop().replace(':00', '');
}

// ---------- as-of view ----------
function asOf(idx) {
  const d = state.data;
  const snap = d.snapshots[idx];
  // The latest position means "now" (the build time), so later milestones count.
  const T = idx === d.snapshots.length - 1 ? Math.max(Date.parse(snap.at), Date.parse(d.generated_at)) : Date.parse(snap.at);
  const selected = new Set(state.hws);
  const fronts = Object.fromEntries(state.hws.map((c) => [c, new Set(cls(snap, c).frontier)]));
  const entries = [];
  for (const e of d.entries) {
    if (!e.available_at || Date.parse(e.available_at) > T || !selected.has(e.hardware_class)) continue;
    const splits = {};
    for (const [k, s] of Object.entries(e.splits)) if (Date.parse(s.completed_at) <= T) splits[k] = s;
    if (!splits.rows) continue;
    const passes = Object.values(splits).every((s) => s.passes);
    const fit = splits.rows.fit_seconds; // the scored fit's time
    entries.push({ ...e, splits, passes, fit, onFrontier: fronts[e.hardware_class].has(e.key),
      isBest: cls(snap, e.hardware_class).best === e.key });
  }
  // Each selected class's best entry (or null), in selection order.
  const bests = Object.fromEntries(state.hws.map((c) => [c, entries.find((e) => e.isBest && e.hardware_class === c) || null]));
  return { T, snap, entries, bests };
}
function visibleEntries(v) {
  return v.entries.filter((e) => state.lines[e.line] && (state.showFailed || e.passes));
}
// An entry's fit time on the frontier: its scored (row-split) fit's.
function fitAsOf(e) {
  return e.splits.rows ? e.splits.rows.fit_seconds : e.fit_seconds;
}
function allSplitsCompleted(T) {
  const out = [];
  for (const e of state.data.entries) {
    for (const s of Object.values(e.splits)) if (Date.parse(s.completed_at) <= T) out.push({ e, s });
  }
  return out;
}

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
// Other processes' mean busy cores during the fit (run records from 3c26c4a on).
const CLEAN_CORES = 0.5;
function timingText(e) {
  if (e.other_cores == null) return 'not recorded';
  const x = e.other_cores;
  return x < CLEAN_CORES ? `clean (${x.toFixed(2)} other cores)` : `contended (${x.toFixed(1)} other cores)`;
}
function entryTip(t, e) {
  const s = e.splits.rows;
  html('div', { class: 't-value' }, t, e.psis ? `${fmtDelta(score(e))} ${fmtSE(scoreErr(e))} PSIS-LOO ΔELPD` : 'no PSIS-LOO score');
  const name = html('div', { class: 't-name' }, t);
  const key = html('span', { class: 'key', style: `background:${LINES[e.line].color}` }, name);
  key.setAttribute('aria-hidden', 'true');
  name.appendChild(document.createTextNode(e.key));
  if (e.design_text) html('div', { class: 't-name' }, t, e.design_text);
  const u = e.splits.units;
  if (e.psis) tipRow(t, 'Pareto k over threshold', `${(100 * e.psis.k_share).toFixed(1)}% of rows`);
  tipRow(t, 'Held-out ΔELPD (vs promoted)', `${fmtDelta(s.delta)} ${fmtSE(s.delta_se)}`);
  tipRow(t, 'Units ΔELPD', u ? `${fmtDelta(u.delta)} ${fmtSE(u.delta_se)}` : 'not run');
  tipRow(t, 'Fit time', fmtDur(e.fit));
  tipRow(t, 'Timing', timingText(e));
  tipRow(t, 'Hardware', e.hardware);
  tipRow(t, 'Chains × draws', drawsText(e));
  tipRow(t, 'Gate', gateText(e));
  tipRow(t, 'Row result landed', fmtWhen.format(Date.parse(s.completed_at)));
  if (e.isBest) tipRow(t, 'Status', 'board best at this date');
  else if (e.onFrontier) tipRow(t, 'Status', 'on the frontier at this date');
  if (e.note) html('div', { class: 't-note' }, t, e.note);
}
function gateText(e) {
  if (e.passes) return 'passes';
  if (e.grade === 'screen') return 'screen-grade (fails gate)';
  const worst = Math.max(...Object.values(e.splits).map((s) => s.max_rhat));
  const grp = Math.max(...Object.values(e.splits).map((s) => s.group_rhat_max || 0));
  const div = Object.values(e.splits).reduce((a, s) => a + (s.divergences || 0), 0);
  return `fails (${div ? `${div} divergence${div > 1 ? 's' : ''}, ` : ''}R-hat ${worst.toFixed(3)}, all-effects ${grp.toFixed(2)})`;
}

// ---------- chart frame ----------
function frame(container, height, margin) {
  container.replaceChildren();
  const width = Math.max(320, container.clientWidth);
  const root = svg('svg', { viewBox: `0 0 ${width} ${height}`, width, height, role: 'img' }, container);
  const inner = { x0: margin.left, x1: width - margin.right, y0: margin.top, y1: height - margin.bottom };
  return { root, width, height, inner };
}
function yGrid(f, y, ticks, fmt) {
  const g = svg('g', { class: 'grid' }, f.root);
  for (const v of ticks) {
    svg('line', { x1: f.inner.x0, x2: f.inner.x1, y1: y(v), y2: y(v) }, g);
    svg('text', { x: f.inner.x0 - 8, y: y(v) + 4, 'text-anchor': 'end', text: fmt(v) }, f.root);
  }
}
function xAxis(f, x, ticks, fmt) {
  svg('line', { class: 'baseline', x1: f.inner.x0, x2: f.inner.x1, y1: f.inner.y1, y2: f.inner.y1 }, f.root);
  for (const v of ticks) {
    svg('line', { class: 'baseline', x1: x(v), x2: x(v), y1: f.inner.y1, y2: f.inner.y1 + 4 }, f.root);
    svg('text', { x: x(v), y: f.inner.y1 + 17, 'text-anchor': 'middle', text: fmt(v) }, f.root);
  }
}
function axisTitles(f, xt, yt) {
  if (xt) svg('text', { class: 'axis-title', x: (f.inner.x0 + f.inner.x1) / 2, y: f.height - 6, 'text-anchor': 'middle', text: xt }, f.root);
  if (yt) svg('text', { class: 'axis-title', x: 14, y: (f.inner.y0 + f.inner.y1) / 2, 'text-anchor': 'middle',
    transform: `rotate(-90 14 ${(f.inner.y0 + f.inner.y1) / 2})`, text: yt }, f.root);
}
// A mark per entry: colour = implementation line, shape = hardware class
// (triangle when clamped below the axis floor), hollow = fails the gate.
function dot(parent, cx, cy, e, opts = {}) {
  const r = opts.r || 5;
  const passes = opts.passes ?? e.passes;
  const color = LINES[e.line].color;
  let node;
  if (opts.clamped) {
    node = svg('polygon', { class: 'dot' + (passes ? '' : ' hollow'), style: passes ? `fill:${color}` : `stroke:${color}`,
      points: `${cx - r},${cy - r} ${cx + r},${cy - r} ${cx},${cy + r}` }, parent);
  } else {
    node = mark(parent, hwShape(e.hardware_class), cx, cy, r, color, passes);
  }
  if (opts.opacity) node.setAttribute('opacity', opts.opacity);
  return node;
}
function nearest(points, px, py, max = HIT) {
  let best = null, bd = Infinity;
  for (const p of points) {
    const d = Math.hypot(p.x - px, p.y - py);
    if (d < bd) { bd = d; best = p; }
  }
  return bd <= max ? best : null;
}
function pointerPos(root, evt) {
  const r = root.getBoundingClientRect();
  const vb = root.viewBox.baseVal;
  return [((evt.clientX - r.left) / r.width) * vb.width, ((evt.clientY - r.top) / r.height) * vb.height];
}
function overlaps(a, b) { return a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h; }
// Place selective direct labels without collisions; leader line when moved away.
function placeLabels(f, items, obstacles) {
  const placed = [];
  const within = (b) => b.x >= f.inner.x0 && b.x + b.w <= f.width - 4 && b.y >= (f.minLabelY ?? 2) && b.y + b.h <= f.inner.y1 - 2;
  for (const it of items) {
    const t = svg('text', { class: it.cls || 'label', x: 0, y: 0, text: it.text }, f.root);
    const bb = t.getBBox();
    const w = bb.width, hgt = bb.height;
    const cands = [[10, -8], [10, 14], [-10 - w, -8], [-10 - w, 14], [-w / 2, -16], [-w / 2, 24], [14, -26], [-14 - w, -26], [14, 34], [-14 - w, 34]];
    let chosen = null;
    for (const [dx, dy] of cands) {
      const box = { x: it.x + dx, y: it.y + dy - hgt + 3, w, h: hgt };
      if (!within(box)) continue;
      if (placed.some((p) => overlaps(p, box)) || obstacles.some((o) => overlaps(o, box))) continue;
      chosen = { dx, dy, box };
      break;
    }
    if (!chosen) { t.remove(); continue; }
    t.setAttribute('x', it.x + chosen.dx);
    t.setAttribute('y', it.y + chosen.dy);
    placed.push(chosen.box);
    if (Math.abs(chosen.dy) > 20) {
      const ly = chosen.dy < 0 ? chosen.box.y + chosen.box.h : chosen.box.y;
      const lx = Math.min(Math.max(it.x, chosen.box.x), chosen.box.x + chosen.box.w);
      const leader = svg('line', { class: 'leader', x1: it.x, y1: it.y + (chosen.dy < 0 ? -6 : 6), x2: lx, y2: ly }, f.root);
      f.root.insertBefore(leader, t);
    }
  }
}

// ---------- domains that stay fixed while scrubbing ----------
function domains() {
  const d0 = state.data;
  // Axes follow the selected hardware (fit times differ by orders of magnitude between machines).
  const d = { ...d0, entries: d0.entries.filter((e) => state.hws.includes(e.hardware_class)) };
  const fits = d.entries.map((e) => e.fit_seconds).concat([d.reference.fit_seconds]);
  const rows = d.entries.map(score).filter((v) => v !== null && v !== undefined);
  const held = d.entries.map(heldout).filter((v) => v !== null && v !== undefined);
  // Default zoom: the baseline sits far below every other entry, so the axis
  // starts just under the lowest non-baseline entry (the baseline is drawn at
  // the floor); "Full range" shows everything.
  const others = d.entries.filter((e) => e.key !== d.baseline_key);
  const rowsNB = others.map(score).filter((v) => v !== null && v !== undefined);
  const heldNB = others.map(heldout).filter((v) => v !== null && v !== undefined);
  const units = d.entries.map((e) => e.splits.units?.delta).filter((v) => v !== null && v !== undefined);
  const maxRows = Math.max(0, ...rows), minRows = Math.min(0, ...rows);
  const maxUnits = Math.max(0, ...units), minUnits = Math.min(0, ...units);
  const times = d.snapshots.map((s) => Date.parse(s.at)).concat([Date.parse(d.reference.available_at)]);
  const t0 = Math.min(...times) - 2 * 3.6e6;
  const t1 = Math.max(...times, ...d.milestones.map((m) => Date.parse(m.at))) + 2 * 3.6e6;
  const zoomFloor = (vals, top) => { const lo = Math.min(...vals); return lo - 0.06 * (top - lo); };
  const floor = state.fullRange || !rowsNB.length || rowsNB.length === rows.length
    ? minRows - 0.04 * Math.max(maxRows - minRows, 1) : zoomFloor(rowsNB, maxRows);
  const ufloor = state.fullRange ? minUnits - 60 : Math.max(minUnits - 60, -150);
  return {
    fit: [Math.min(...fits) / 1.6, Math.max(...fits) * 1.6],
    rows: [floor, maxRows + 0.04 * Math.max(maxRows - floor, 1)],
    held: state.fullRange || !heldNB.length
      ? [Math.min(0, ...held) - 60, Math.max(0, ...held) + 70]
      : [zoomFloor(heldNB, Math.max(...held)), Math.max(0, ...held) + 70],
    units: [ufloor, maxUnits + 80],
    time: [t0, t1],
  };
}

// ---------- charts ----------
function staircase(points, x, y, xEnd) {
  const pts = [...points].sort((a, b) => a.fit - b.fit);
  if (!pts.length) return null;
  let path = `M${x(pts[0].fit)},${y(score(pts[0]))}`;
  for (let i = 1; i < pts.length; i++) {
    path += ` H${x(pts[i].fit)} V${y(score(pts[i]))}`;
  }
  path += ` H${xEnd}`;
  return { path, first: pts[0] };
}

function drawFrontier(v, dom) {
  const container = $('chart-frontier');
  const f = frame(container, 440, { top: 18, right: 24, bottom: 46, left: 76 });
  const x = logScale(dom.fit, [f.inner.x0, f.inner.x1]);
  const y = linear(dom.rows, [f.inner.y1, f.inner.y0]);
  f.root.setAttribute('aria-label', 'Scatter of PSIS-LOO ΔELPD against fit time with the Pareto frontier');
  yGrid(f, y, niceTicks(...dom.rows, 7), (t) => fmtDelta(t, 0));
  xAxis(f, x, durationTicks(dom.fit), fmtDurTick);
  axisTitles(f, 'Fit time of the scored fit (log scale)', 'PSIS-LOO ΔELPD vs baseline');
  const clampY = (val) => Math.max(val, dom.rows[0]);

  // Latest frontiers as ghosts when scrubbed back in time.
  const last = state.data.snapshots.length - 1;
  const multi = state.hws.length > 1;
  if (state.idx < last) {
    const latest = asOf(last).entries.filter((e) => e.onFrontier);
    for (const c of state.hws) {
      const g = staircase(latest.filter((e) => e.hardware_class === c), x, (val) => y(clampY(val)), f.inner.x1);
      if (g) svg('path', { class: 'ghost-line', d: g.path, 'stroke-dasharray': dashOf(c) }, f.root);
    }
  }
  // One frontier per selected hardware class: a fit time only competes with
  // fit times on the same hardware.
  const front = v.entries.filter((e) => e.onFrontier);
  const ends = [];
  for (const c of state.hws) {
    const fc = front.filter((e) => e.hardware_class === c);
    const st = staircase(fc, x, (val) => y(clampY(val)), f.inner.x1);
    if (!st) continue;
    if (!multi) svg('path', { class: 'frontier-wash', d: `${st.path} V${f.inner.y1} H${x(st.first.fit)} Z` }, f.root);
    svg('path', { class: 'frontier-line', d: st.path, 'stroke-dasharray': dashOf(c) }, f.root);
    const top = [...fc].sort((a, b) => b.fit - a.fit)[0];
    ends.push({ c, y: y(clampY(score(top))) });
  }
  // The 15-minute window.
  if (FIT_WINDOW > dom.fit[0] && FIT_WINDOW < dom.fit[1]) {
    const wx = x(FIT_WINDOW);
    svg('line', { class: 'ref-line', x1: wx, x2: wx, y1: f.inner.y0, y2: f.inner.y1 }, f.root);
    svg('text', { class: 'label-muted', x: wx - 4, y: f.inner.y1 - 6, 'text-anchor': 'end', text: '≤ 15 min per fit' }, f.root);
  }
  // Baseline (dELPD 0) hairline, when 0 is on the axis (not in the default zoom).
  const zeroOnAxis = dom.rows[0] <= 0;
  if (zeroOnAxis) svg('line', { class: 'ref-line', x1: f.inner.x0, x2: f.inner.x1, y1: y(0), y2: y(0) }, f.root);

  const pts = [];
  const shown = visibleEntries(v);
  for (const e of shown) {
    const val = score(e), err = scoreErr(e);
    if (val === null) continue;
    const cx = x(e.fit), clamped = val < dom.rows[0], cy = y(clampY(val));
    if (state.showSE && err && !clamped) {
      svg('line', { class: 'se', x1: cx, x2: cx, y1: y(clampY(val - err)), y2: y(Math.min(val + err, dom.rows[1])),
        style: `stroke:${LINES[e.line].color}` }, f.root);
    }
    pts.push({ x: cx, y: cy, e, clamped });
  }
  // Draw failing first so passing marks sit on top.
  pts.sort((a, b) => Number(a.e.passes) - Number(b.e.passes));
  for (const p of pts) {
    const node = dot(f.root, p.x, p.y, p.e, { clamped: p.clamped, r: p.e.isBest ? 6 : 5 });
    node.setAttribute('tabindex', '0');
    node.setAttribute('aria-label', `${p.e.key}: ${fmtDelta(score(p.e))} PSIS-LOO ΔELPD, ${fmtDur(p.e.fit)}`);
    node.addEventListener('focus', () => {
      const r = node.getBoundingClientRect();
      showTip({ clientX: r.right, clientY: r.bottom }, (t) => entryTip(t, p.e));
    });
    node.addEventListener('blur', hideTip);
    p.node = node;
  }
  // Selective direct labels: frontier members and the best.
  const obstacles = pts.map((p) => ({ x: p.x - 6, y: p.y - 6, w: 12, h: 12 }));
  if (zeroOnAxis) obstacles.push({ x: f.inner.x0, y: y(0) - 2, w: f.inner.x1 - f.inner.x0, h: 4 });
  for (const c of state.hws) {
    const steps = front.filter((e) => e.hardware_class === c).sort((a, b) => a.fit - b.fit);
    steps.forEach((e, i) => {
      const sx = x(e.fit), ex = i + 1 < steps.length ? x(steps[i + 1].fit) : f.inner.x1;
      const sy = y(clampY(score(e)));
      obstacles.push({ x: sx, y: sy - 3, w: ex - sx, h: 6 });
      if (i + 1 < steps.length) {
        const ny = y(clampY(score(steps[i + 1])));
        obstacles.push({ x: ex - 3, y: Math.min(sy, ny), w: 6, h: Math.abs(sy - ny) });
      }
    });
  }
  const items = [];
  // Name each staircase at its right end when several classes are shown.
  if (multi) for (const end of ends) items.push({ x: f.inner.x1 - 2, y: end.y, text: `${hwShort(end.c)} frontier` });
  for (const best of pts.filter((p) => p.e.isBest)) {
    items.push({ x: best.x, y: best.y, text: `Best${multi ? ` (${hwShort(best.e.hardware_class)})` : ''}: ${entryLabel(best.e)}` });
  }
  for (const p of pts.filter((q) => q.e.onFrontier && !q.e.isBest).sort((a, b) => score(b.e) - score(a.e))) {
    items.push({ x: p.x, y: p.y, text: entryLabel(p.e) + (p.clamped ? ` (${fmtDelta(score(p.e), 0)})` : '') });
  }
  placeLabels(f, items, obstacles);

  // Hover: nearest point within the hit radius.
  let lifted = null;
  f.root.addEventListener('pointermove', (evt) => {
    const [px, py] = pointerPos(f.root, evt);
    const hit = nearest(pts, px, py);
    if (lifted) lifted.classList.remove('lift');
    lifted = null;
    if (!hit) return hideTip();
    hit.node.classList.add('lift');
    lifted = hit.node;
    showTip(evt, (t) => entryTip(t, hit.e));
  });
  f.root.addEventListener('pointerleave', () => { hideTip(); if (lifted) lifted.classList.remove('lift'); });

  renderTable($('table-frontier'), ['Entry', 'PSIS-LOO ΔELPD', '± (SE + MC)', 'k over threshold', 'Fit time', 'Hardware', 'Gate', 'Frontier'],
    [...pts].sort((a, b) => score(b.e) - score(a.e)).map((p) => [p.e.key, fmtDelta(score(p.e)), scoreErr(p.e).toFixed(1),
      `${(100 * p.e.psis.k_share).toFixed(1)}%`, fmtDur(p.e.fit), p.e.hardware, gateText(p.e), p.e.onFrontier ? 'yes' : '']),
    [1, 2, 3, 4]);
}

function drawUnits(v, dom) {
  const container = $('chart-units');
  const f = frame(container, 300, { top: 14, right: 20, bottom: 44, left: 62 });
  const x = logScale(dom.fit, [f.inner.x0, f.inner.x1]);
  const y = linear(dom.units, [f.inner.y1, f.inner.y0]);
  f.root.setAttribute('aria-label', 'Scatter of unit-split ΔELPD against fit time');
  yGrid(f, y, niceTicks(...dom.units, 5), (t) => fmtDelta(t, 0));
  xAxis(f, x, durationTicks(dom.fit), fmtDurTick);
  axisTitles(f, 'Fit time (log scale)', 'Unit-split ΔELPD');
  svg('line', { class: 'ref-line', x1: f.inner.x0, x2: f.inner.x1, y1: y(0), y2: y(0) }, f.root);
  const pts = [];
  for (const e of visibleEntries(v)) {
    const s = e.splits.units;
    if (!s || s.delta === null) continue;
    const clamped = s.delta < dom.units[0];
    const cx = x(e.fit), cy = y(Math.max(s.delta, dom.units[0]));
    if (state.showSE && s.delta_se && !clamped) {
      svg('line', { class: 'se', x1: cx, x2: cx, y1: y(Math.max(s.delta - s.delta_se, dom.units[0])), y2: y(Math.min(s.delta + s.delta_se, dom.units[1])),
        style: `stroke:${LINES[e.line].color}` }, f.root);
    }
    pts.push({ x: cx, y: cy, e, clamped });
  }
  pts.sort((a, b) => Number(a.e.passes) - Number(b.e.passes));
  for (const p of pts) p.node = dot(f.root, p.x, p.y, p.e, { clamped: p.clamped });
  const obstacles = pts.map((p) => ({ x: p.x - 6, y: p.y - 6, w: 12, h: 12 }));
  placeLabels(f, pts.filter((p) => p.e.isBest).map((p) => ({ x: p.x, y: p.y,
    text: `Best${state.hws.length > 1 ? ` (${hwShort(p.e.hardware_class)})` : ''}: ${entryLabel(p.e)}` })), obstacles);
  hoverPoints(f, pts, (t, p) => {
    const s = p.e.splits.units;
    html('div', { class: 't-value' }, t, `${fmtDelta(s.delta)} ${fmtSE(s.delta_se)} units ΔELPD`);
    html('div', { class: 't-name' }, t, p.e.key);
    tipRow(t, 'PSIS-LOO ΔELPD', fmtDelta(score(p.e)));
    tipRow(t, 'Fit time', fmtDur(p.e.fit));
    if (s.rescore) tipRow(t, 'Exact rescore', `≈ ${fmtDelta(s.rescore.exact_recorded_equivalent)}`);
  });
  renderTable($('table-units'), ['Entry', 'Units ΔELPD', 'SE', 'Exact rescore', 'Fit time'],
    pts.map((p) => [p.e.key, fmtDelta(p.e.splits.units.delta), p.e.splits.units.delta_se?.toFixed(1) ?? '',
      p.e.splits.units.rescore ? fmtDelta(p.e.splits.units.rescore.exact_recorded_equivalent) : '', fmtDur(p.e.fit)]), [1, 2, 3, 4]);
}

function drawValidation(v, dom) {
  const container = $('chart-validation');
  const f = frame(container, 300, { top: 14, right: 20, bottom: 44, left: 62 });
  const x = linear(dom.rows, [f.inner.x0, f.inner.x1]);
  const y = linear(dom.held, [f.inner.y1, f.inner.y0]);
  f.root.setAttribute('aria-label', 'PSIS-LOO ΔELPD against held-out ΔELPD per entry');
  yGrid(f, y, niceTicks(...dom.held, 5), (t) => fmtDelta(t, 0));
  xAxis(f, x, niceTicks(...dom.rows, 6), (t) => fmtDelta(t, 0));
  axisTitles(f, 'PSIS-LOO ΔELPD vs baseline (training rows)', 'Held-out ΔELPD vs promoted');
  const pts = [];
  for (const e of visibleEntries(v)) {
    const a = score(e), b = heldout(e);
    if (a === null || b === null) continue;
    const clamped = a < dom.rows[0] || b < dom.held[0];
    pts.push({ x: x(Math.max(a, dom.rows[0])), y: y(Math.max(b, dom.held[0])), e, a, b, clamped });
  }
  pts.sort((p, q) => Number(p.e.passes) - Number(q.e.passes));
  for (const p of pts) p.node = dot(f.root, p.x, p.y, p.e, { clamped: p.clamped });
  // Spearman rank correlation, as a one-number summary of agreement.
  const rank = (arr) => { const o = arr.map((v2, i) => [v2, i]).sort((m, n) => m[0] - n[0]); const r = []; o.forEach(([, i], k) => { r[i] = k; }); return r; };
  const both = v.entries.filter((e) => score(e) !== null && heldout(e) !== null);
  let rho = null;
  if (both.length > 2) {
    const ra = rank(both.map(score)), rb = rank(both.map(heldout)), n = both.length;
    rho = 1 - (6 * ra.reduce((acc, r, i) => acc + (r - rb[i]) ** 2, 0)) / (n * (n * n - 1));
  }
  $('validation-caption').textContent = rho === null ? '' :
    `Spearman rank correlation across the ${both.length} entries scored both ways: ${rho.toFixed(2)}.`;
  hoverPoints(f, pts, (t, p) => {
    html('div', { class: 't-value' }, t, `${fmtDelta(p.a)} PSIS-LOO · ${fmtDelta(p.b)} held-out`);
    html('div', { class: 't-name' }, t, p.e.key);
    tipRow(t, 'Held-out mean lpd', p.e.psis.validation.heldout_mean_lpd.toFixed(4));
    tipRow(t, 'PSIS mean lpd (multi-row units)', p.e.psis.validation.psis_mean_lpd_multi_row_units.toFixed(4));
  });
  renderTable($('table-validation'), ['Entry', 'PSIS-LOO ΔELPD', 'Held-out ΔELPD', 'Held-out mean lpd', 'PSIS mean lpd (multi-row units)'],
    pts.map((p) => [p.e.key, fmtDelta(p.a), fmtDelta(p.b), p.e.psis.validation.heldout_mean_lpd.toFixed(4),
      p.e.psis.validation.psis_mean_lpd_multi_row_units.toFixed(4)]), [1, 2, 3, 4]);
}

const VAR_LABEL = {
  'market and time': 'Market and time', features: 'Features', building: 'Building level',
  'building over time': 'Building over time', 'building slopes': 'Building slopes', unit: 'Unit effects', residual: 'Residual',
};
const VAR_INK = ['#ffffff', '#ffffff', '#0b0b0b', '#0b0b0b', '#0b0b0b', '#ffffff', '#ffffff']; // text on each fill

function drawVariance(v) {
  const groups = state.data.variance_groups;
  const legend = $('legend-variance');
  legend.replaceChildren();
  groups.forEach((g, i) => {
    const it = html('span', { class: 'item' }, legend);
    html('span', { class: 'rect', style: `background:var(--cat-${i + 1})`, 'aria-hidden': 'true' }, it);
    it.appendChild(document.createTextNode(VAR_LABEL[g]));
  });
  const rowsE = v.entries.filter((e) => e.variance && (e.onFrontier || e.isBest)).sort((a, b) => a.fit - b.fit);
  const container = $('chart-variance');
  if (!rowsE.length) {
    container.replaceChildren();
    html('p', { class: 'caption' }, container, 'No frontier entry with a variance decomposition on this hardware yet.');
    $('table-variance').replaceChildren();
    return;
  }
  const barH = 20, gap = 12, labelW = 230;
  const f = frame(container, 16 + rowsE.length * (barH + gap) + 30, { top: 8, right: 16, bottom: 30, left: labelW });
  f.root.setAttribute('aria-label', 'Stacked bars of variance shares per frontier entry');
  const x = linear([0, 1], [f.inner.x0, f.inner.x1]);
  for (const t of [0, 0.25, 0.5, 0.75, 1]) {
    svg('line', { class: 'grid-line', x1: x(t), x2: x(t), y1: f.inner.y0, y2: f.inner.y1, style: 'stroke:var(--grid)' }, f.root);
    svg('text', { x: x(t), y: f.inner.y1 + 16, 'text-anchor': 'middle', text: `${t * 100}%` }, f.root);
  }
  const segs = [];
  rowsE.forEach((e, r) => {
    const y0 = f.inner.y0 + 8 + r * (barH + gap);
    svg('text', { class: 'label', x: labelW - 10, y: y0 + barH / 2 + 4, 'text-anchor': 'end',
      text: entryLabel(e) + (state.hws.length > 1 ? ` · ${hwShort(e.hardware_class)}` : '') + (e.isBest ? ' (best)' : '') }, f.root);
    let acc = 0;
    groups.forEach((g, i) => {
      const share = Math.max(0, e.variance[g].mean);
      const x0 = x(acc), x1 = x(Math.min(1, acc + share));
      acc += share;
      const w = Math.max(0, x1 - x0 - 2); // 2px surface gap between segments
      if (w <= 0) return;
      const node = svg('rect', { x: x0, y: y0, width: w, height: barH, rx: i === groups.length - 1 ? 4 : 0,
        style: `fill:var(--cat-${i + 1})` }, f.root);
      const text = `${(100 * e.variance[g].mean).toFixed(0)}%`;
      if (w > 30) svg('text', { x: x0 + w / 2, y: y0 + barH / 2 + 4, 'text-anchor': 'middle', text, style: `fill:${VAR_INK[i]};font-size:11px` }, f.root);
      segs.push({ x0, x1: x0 + w, y0, y1: y0 + barH, e, g, node });
    });
  });
  f.root.addEventListener('pointermove', (evt) => {
    const [px, py] = pointerPos(f.root, evt);
    const hit = segs.find((sgm) => px >= sgm.x0 - 1 && px <= sgm.x1 + 1 && py >= sgm.y0 - gap / 2 && py <= sgm.y1 + gap / 2);
    if (!hit) return hideTip();
    const iv = hit.e.variance[hit.g];
    showTip(evt, (t) => {
      html('div', { class: 't-value' }, t, `${(100 * iv.mean).toFixed(1)}% of the variation`);
      html('div', { class: 't-name' }, t, `${VAR_LABEL[hit.g]} · ${hit.e.key}`);
      tipRow(t, '90% interval', `${(100 * iv.lower_90).toFixed(1)}–${(100 * iv.upper_90).toFixed(1)}%`);
    });
  });
  f.root.addEventListener('pointerleave', hideTip);
  renderTable($('table-variance'), ['Entry', ...groups.map((g) => VAR_LABEL[g])],
    rowsE.map((e) => [e.key, ...groups.map((g) => `${(100 * e.variance[g].mean).toFixed(1)}%`)]), groups.map((_, i) => i + 1));
}

// ---------- same structure, different implementations ----------
const HW_MARKS = [
  { test: (c) => c.includes('2060'), shape: 'circle', label: 'thelio RTX 2060 SUPER' },
  { test: (c) => c.startsWith('thelio CPU'), shape: 'square', label: 'thelio CPU' },
  { test: () => true, shape: 'diamond', label: 'Modal (H100 / H200 / CPU)' },
];
const hwShape = (cls) => HW_MARKS.find((m) => m.test(cls)).shape;
const LINE_ORDER = ['frontier', 'pymc', 'numpyro'];
function mark(parent, shape, cx, cy, r, color, passes) {
  const attrs = { class: 'dot' + (passes ? '' : ' hollow'), style: passes ? `fill:${color}` : `stroke:${color}` };
  if (shape === 'circle') return svg('circle', { ...attrs, cx, cy, r }, parent);
  if (shape === 'square') return svg('rect', { ...attrs, x: cx - r * 0.9, y: cy - r * 0.9, width: 1.8 * r, height: 1.8 * r, rx: 1.5 }, parent);
  const d = r * 1.25;
  return svg('polygon', { ...attrs, points: `${cx},${cy - d} ${cx + d},${cy} ${cx},${cy + d} ${cx - d},${cy}` }, parent);
}
// Every landed entry at time T on every hardware class (the chart spans classes).
function entriesAllHardware(T) {
  const out = [];
  for (const e of state.data.entries) {
    if (!e.available_at || Date.parse(e.available_at) > T) continue;
    const splits = {};
    for (const [k, s] of Object.entries(e.splits)) if (Date.parse(s.completed_at) <= T) splits[k] = s;
    if (!splits.rows) continue;
    out.push({ ...e, splits, passes: Object.values(splits).every((s) => s.passes), fit: splits.rows.fit_seconds });
  }
  return out;
}
function drawImplementations(v) {
  const byStruct = new Map();
  for (const e of entriesAllHardware(v.T)) {
    if (!state.lines[e.line] || !e.structure) continue;
    const g = byStruct.get(e.structure) || new Map();
    const k = `${e.line}|${e.hardware_class}`;
    const prev = g.get(k);
    if (!prev || Date.parse(e.available_at) > Date.parse(prev.available_at)) g.set(k, e);
    byStruct.set(e.structure, g);
  }
  const rows = [...byStruct.entries()].filter(([, g]) => g.size > 1).map(([s, g]) => {
    const marks = [...g.values()];
    const scored = marks.filter((e) => e.passes && score(e) !== null).map(score);
    const alias = [...new Set(marks.filter((e) => e.line !== 'frontier' && !s.startsWith(e.design + '/')).map((e) => e.design))];
    return { s, marks, alias, spread: scored.length > 1 ? Math.max(...scored) - Math.min(...scored) : null,
      order: Math.max(...marks.map((e) => score(e) ?? -Infinity)) };
  }).sort((a, b) => a.order - b.order);
  const legend = $('legend-impl');
  legend.replaceChildren();
  for (const key of LINE_ORDER) {
    const it = html('span', { class: 'item' }, legend);
    html('span', { class: 'rect', style: `background:${LINES[key].color}`, 'aria-hidden': 'true' }, it);
    it.appendChild(document.createTextNode(LINES[key].label));
  }
  for (const m of HW_MARKS) {
    const it = html('span', { class: 'item' }, legend);
    const s = svg('svg', { width: 14, height: 14, viewBox: '0 0 14 14' }, it);
    mark(s, m.shape, 7, 7, 4.5, 'var(--text-secondary)', true);
    it.appendChild(document.createTextNode(m.label));
  }
  const container = $('chart-impl');
  if (!rows.length) {
    container.replaceChildren();
    html('p', { class: 'caption' }, container, 'No structure has been fit by more than one implementation or on more than one kind of hardware yet.');
    $('table-impl').replaceChildren();
    return;
  }
  const rowH = 34, labelW = 250, rightW = 150;
  const f = frame(container, 20 + rows.length * rowH + 40, { top: 12, right: rightW, bottom: 40, left: labelW });
  f.root.setAttribute('aria-label', 'Fit time of each implementation of each model structure');
  const fits = rows.flatMap((r) => r.marks.map((e) => e.fit));
  const x = logScale([Math.min(...fits) / 1.6, Math.max(...fits) * 1.6], [f.inner.x0, f.inner.x1]);
  const ticks = durationTicks([Math.min(...fits) / 1.6, Math.max(...fits) * 1.6]);
  for (const t of ticks) svg('line', { x1: x(t), x2: x(t), y1: f.inner.y0, y2: f.inner.y1, style: 'stroke:var(--grid)' }, f.root);
  xAxis(f, x, ticks, fmtDurTick);
  axisTitles(f, 'Fit time (log scale)', null);
  svg('text', { class: 'label-muted', x: f.inner.x1 + 12, y: f.inner.y0 + 2, text: 'PSIS-LOO spread' }, f.root);
  const pts = [];
  rows.forEach((r, i) => {
    const cy = f.inner.y0 + 14 + i * rowH;
    svg('line', { x1: f.inner.x0, x2: f.inner.x1, y1: cy, y2: cy, style: 'stroke:var(--grid);stroke-dasharray:2 3' }, f.root);
    const [design, feats] = r.s.split('/');
    svg('text', { class: 'label', x: labelW - 10, y: cy + 4, 'text-anchor': 'end',
      text: `${design}${r.alias.length ? ` (= ${r.alias.join(', ')})` : ''} · ${feats}` }, f.root);
    svg('text', { class: 'label-muted', x: f.inner.x1 + 12, y: cy + 4,
      text: r.spread === null ? '—' : `${r.spread.toFixed(1)} nats` }, f.root);
    for (const e of r.marks.sort((a, b) => LINE_ORDER.indexOf(a.line) - LINE_ORDER.indexOf(b.line))) {
      const cy2 = cy + (LINE_ORDER.indexOf(e.line) - 1) * 7;
      const node = mark(f.root, hwShape(e.hardware_class), x(e.fit), cy2, 5.5, LINES[e.line].color, e.passes);
      pts.push({ x: x(e.fit), y: cy2, e, node });
    }
  });
  hoverPoints(f, pts, (t, p) => entryTip(t, p.e));
  renderTable($('table-impl'), ['Structure', 'Implementation', 'Hardware', 'Fit time', 'PSIS-LOO ΔELPD', 'Gate', 'Timing'],
    rows.flatMap((r) => r.marks.map((e) => [r.s, LINES[e.line].label, e.hardware_class, fmtDur(e.fit),
      e.psis ? `${fmtDelta(score(e))} ${fmtSE(scoreErr(e))}` : '—', gateText(e), timingText(e)])), [3, 4]);
}

function hoverPoints(f, pts, build) {
  let lifted = null;
  f.root.addEventListener('pointermove', (evt) => {
    const [px, py] = pointerPos(f.root, evt);
    const hit = nearest(pts, px, py);
    if (lifted) lifted.classList.remove('lift');
    lifted = null;
    if (!hit) return hideTip();
    if (hit.node) { hit.node.classList.add('lift'); lifted = hit.node; }
    showTip(evt, (t) => build(t, hit));
  });
  f.root.addEventListener('pointerleave', () => { hideTip(); if (lifted) lifted.classList.remove('lift'); });
}

function timeFrame(container, height, dom, yScaleFn, yTicks, yFmt, yTitle, label) {
  const f = frame(container, height, { top: 30, right: 28, bottom: 44, left: 76 });
  f.minLabelY = 26; // keep direct labels clear of the milestone ticks
  f.root.setAttribute('aria-label', label);
  const x = linear(dom.time, [f.inner.x0, f.inner.x1]);
  const y = yScaleFn([f.inner.y1, f.inner.y0]);
  yGrid(f, y, yTicks, yFmt);
  xAxis(f, x, timeTicks(dom.time, f.width), timeTickLabel);
  axisTitles(f, `Time landed (${state.data.timezone.replace('_', ' ')})`, yTitle);
  // Milestone ticks along the top band.
  const ms = [];
  for (const m of state.data.milestones) {
    const t = Date.parse(m.at);
    if (t < dom.time[0] || t > dom.time[1]) continue;
    const mx = x(t);
    svg('line', { class: m.kind === 'selection' ? 'ms-sel' : 'ms-pr', x1: mx, x2: mx, y1: 6, y2: m.kind === 'selection' ? 22 : 18 }, f.root);
    ms.push({ x: mx, y: 14, m });
  }
  return { f, x, y, ms };
}
function cursorAt(tf, T) {
  const cx = tf.x(T);
  svg('line', { class: 'cursor', x1: cx, x2: cx, y1: tf.f.inner.y0, y2: tf.f.inner.y1 }, tf.f.root);
}
function milestoneTip(t, m) {
  html('div', { class: 't-value' }, t, m.kind === 'selection' ? 'App model selected' : `PR #${m.pr} merged`);
  html('div', { class: 't-name' }, t, m.title);
  if (m.model) tipRow(t, 'Model', m.model);
  tipRow(t, 'When', fmtWhen.format(Date.parse(m.at)));
  tipRow(t, 'Commit', m.sha);
}
function bestAtTime(T) {
  const snaps = state.data.snapshots;
  let i = -1;
  for (let k = 0; k < snaps.length; k++) if (Date.parse(snaps[k].at) <= T) i = k;
  return i;
}
function timeHover(tf, pts, onTime) {
  const hl = svg('line', { class: 'hover-line', x1: 0, x2: 0, y1: tf.f.inner.y0, y2: tf.f.inner.y1, visibility: 'hidden' }, tf.f.root);
  let lifted = null;
  tf.f.root.addEventListener('pointermove', (evt) => {
    const [px, py] = pointerPos(tf.f.root, evt);
    if (lifted) lifted.classList.remove('lift');
    lifted = null;
    if (py < tf.f.inner.y0) {
      hl.setAttribute('visibility', 'hidden');
      const m = nearest(tf.ms, px, 14, 8);
      return m ? showTip(evt, (t) => milestoneTip(t, m.m)) : hideTip();
    }
    const hit = nearest(pts, px, py);
    if (hit) {
      hl.setAttribute('visibility', 'hidden');
      if (hit.node) { hit.node.classList.add('lift'); lifted = hit.node; }
      return showTip(evt, (t) => entryTip(t, hit.e));
    }
    if (px < tf.f.inner.x0 || px > tf.f.inner.x1) { hl.setAttribute('visibility', 'hidden'); return hideTip(); }
    hl.setAttribute('x1', px); hl.setAttribute('x2', px); hl.setAttribute('visibility', 'visible');
    const T = tf.x.invert(px);
    showTip(evt, (t) => onTime(t, T));
  });
  tf.f.root.addEventListener('pointerleave', () => { hideTip(); hl.setAttribute('visibility', 'hidden'); if (lifted) lifted.classList.remove('lift'); });
  tf.f.root.addEventListener('click', (evt) => {
    const [px, py] = pointerPos(tf.f.root, evt);
    if (px < tf.f.inner.x0 || px > tf.f.inner.x1 || py < tf.f.inner.y0) return;
    const i = bestAtTime(tf.x.invert(px));
    if (i >= 0) setIdx(i);
  });
}

function timeDots(tf, v, yOf, dom) {
  const pts = [];
  const all = state.data.entries.filter((e) => e.available_at && state.lines[e.line]);
  for (const e0 of all) {
    const t = Date.parse(e0.available_at);
    const cur = v.entries.find((e) => e.key === e0.key);
    const e = cur || { ...e0, passes: e0.passes_checks, fit: e0.fit_seconds, splits: e0.splits };
    if (!state.showFailed && !e.passes) continue;
    const val = yOf(e);
    if (val === null || val === undefined) continue;
    const clamped = val < dom[0];
    const p = { x: tf.x(t), y: tf.y(Math.max(val, dom[0])), e, clamped };
    p.node = dot(tf.f.root, p.x, p.y, e, { clamped, opacity: cur ? null : 0.18 });
    if (cur) pts.push(p);
  }
  return pts;
}

function drawProgress(v, dom) {
  const tf = timeFrame($('chart-progress'), 360, dom, (r) => linear(dom.rows, r), niceTicks(...dom.rows, 6), (t) => fmtDelta(t, 0),
    'PSIS-LOO ΔELPD', 'Best PSIS-LOO ΔELPD over time with every scored entry');
  const zeroOnAxis = dom.rows[0] <= 0;
  if (zeroOnAxis) svg('line', { class: 'ref-line', x1: tf.f.inner.x0, x2: tf.f.inner.x1, y1: tf.y(0), y2: tf.y(0) }, tf.f.root);
  // Each selected class's best, as a staircase up to the as-of time.
  const snaps = state.data.snapshots.slice(0, state.idx + 1);
  const multi = state.hws.length > 1;
  for (const c of state.hws) {
    let d = '';
    let prev = null;
    for (const s of snaps) {
      if (cls(s, c).best_delta === null) continue;
      const sx = tf.x(Date.parse(s.at)), sy = tf.y(Math.max(cls(s, c).best_delta, dom.rows[0]));
      d += prev ? ` H${sx} V${sy}` : `M${sx},${sy}`;
      prev = s;
    }
    if (prev) svg('path', { class: 'best-line', d: d + ` H${tf.x(v.T)}`, 'stroke-dasharray': dashOf(c) }, tf.f.root);
  }
  const pts = timeDots(tf, v, score, dom.rows);
  cursorAt(tf, v.T);
  const obstacles = pts.map((q) => ({ x: q.x - 6, y: q.y - 6, w: 12, h: 12 }));
  const labels = [];
  for (const b of Object.values(v.bests)) {
    const p = b && pts.find((q) => q.e.key === b.key);
    if (p) labels.push({ x: p.x, y: p.y, text: `${multi ? `${hwShort(b.hardware_class)}: ` : ''}${entryLabel(p.e)} ${fmtDelta(score(p.e))}` });
  }
  placeLabels(tf.f, labels, obstacles);
  if (zeroOnAxis) svg('text', { class: 'label-muted', x: tf.f.inner.x1 - 4, y: tf.y(0) - 6, 'text-anchor': 'end', text: 'baseline (m0-base) = 0' }, tf.f.root);
  timeHover(tf, pts, (t, T) => {
    const i = bestAtTime(T);
    html('div', { class: 't-name' }, t, `Board best at ${fmtWhen.format(T)}`);
    for (const c of state.hws) {
      const h = i >= 0 ? cls(state.data.snapshots[i], c) : EMPTY;
      tipRow(t, hwShort(c), h.best ? `${fmtDelta(h.best_delta)} · ${h.best} (${h.frontier.length} on the frontier)` : 'no gate-passing entry');
    }
  });
  const rows = [];
  for (const c of state.hws) {
    let last = null;
    for (const s of snaps) {
      const h = cls(s, c);
      if (h.best === last) continue;
      last = h.best;
      if (h.best) rows.push([fmtWhen.format(Date.parse(s.at)), hwShort(c), h.best, fmtDelta(h.best_delta), String(h.frontier.length), Date.parse(s.at)]);
    }
  }
  rows.sort((a, b) => a[5] - b[5]);
  renderTable($('table-progress'), ['Became best', 'Hardware', 'Entry', 'PSIS-LOO ΔELPD', 'Frontier size'], rows.map((r) => r.slice(0, 5)), [3, 4]);
}

function drawFitTime(v, dom) {
  const tf = timeFrame($('chart-time'), 320, dom, (r) => logScale(dom.fit, r), durationTicks(dom.fit), fmtDurTick,
    'Fit time (log scale)', 'Fit time of each entry over time');
  const ref = state.data.reference;
  svg('line', { class: 'ref-line', x1: tf.f.inner.x0, x2: tf.f.inner.x1, y1: tf.y(ref.fit_seconds), y2: tf.y(ref.fit_seconds) }, tf.f.root);
  svg('text', { class: 'label-muted', x: tf.f.inner.x1 - 4, y: tf.y(ref.fit_seconds) - 6, 'text-anchor': 'end',
    text: `promoted reference full fit ≈ ${fmtDur(ref.fit_seconds)} (CPU)` }, tf.f.root);
  // Fit time of each selected class's best, as a staircase.
  const byKey = Object.fromEntries(state.data.entries.map((e) => [e.key, e]));
  for (const c of state.hws) {
    let d = '', prev = null;
    for (const s of state.data.snapshots.slice(0, state.idx + 1)) {
      if (!cls(s, c).best) continue;
      const T = Date.parse(s.at);
      const sx = tf.x(T), sy = tf.y(fitAsOf(byKey[cls(s, c).best], T));
      d += prev ? ` H${sx} V${sy}` : `M${sx},${sy}`;
      prev = s;
    }
    if (prev) svg('path', { class: 'best-line', d: d + ` H${tf.x(v.T)}`, 'stroke-dasharray': dashOf(c) }, tf.f.root);
  }
  const pts = timeDots(tf, v, (e) => e.fit, [dom.fit[0]]);
  cursorAt(tf, v.T);
  timeHover(tf, pts, (t, T) => {
    const i = bestAtTime(T);
    html('div', { class: 't-name' }, t, `Fit time of the board best at ${fmtWhen.format(T)}`);
    for (const c of state.hws) {
      const s = i >= 0 ? cls(state.data.snapshots[i], c) : EMPTY;
      tipRow(t, hwShort(c), s.best ? `${fmtDur(fitAsOf(byKey[s.best]))} · ${s.best}` : '—');
    }
  });
  renderTable($('table-time'), ['Landed', 'Entry', 'Fit time', 'Hardware'],
    pts.sort((a, b) => a.x - b.x).map((p) => [fmtWhen.format(Date.parse(p.e.available_at)), p.e.key, fmtDur(p.e.fit), p.e.hardware]), [2]);
}

function drawCompute(v, dom) {
  const runs = allSplitsCompleted(Infinity).sort((a, b) => Date.parse(a.s.completed_at) - Date.parse(b.s.completed_at));
  const totals = { frontier: 0, pymc: 0, numpyro: 0 };
  const series = { frontier: [], pymc: [], numpyro: [] };
  for (const { e, s } of runs) {
    totals[e.line] += s.fit_seconds / 3600;
    series[e.line].push({ t: Date.parse(s.completed_at), h: totals[e.line], e, s });
  }
  const maxH = Math.max(totals.frontier, totals.pymc, totals.numpyro, 1);
  const tf = timeFrame($('chart-compute'), 300, dom, (r) => linear([0, maxH * 1.12], r), niceTicks(0, maxH * 1.12, 5), (t) => `${t} h`,
    'Cumulative fit hours', 'Cumulative fit hours by model line');
  const endLabels = [];
  for (const line of Object.keys(LINES)) {
    if (!state.lines[line]) continue;
    const pts = series[line].filter((p) => p.t <= v.T);
    if (!pts.length) continue;
    let d = `M${tf.x(pts[0].t)},${tf.y(0)} V${tf.y(pts[0].h)}`;
    for (const p of pts.slice(1)) d += ` H${tf.x(p.t)} V${tf.y(p.h)}`;
    d += ` H${tf.x(v.T)}`;
    svg('path', { class: 'series-line', d, style: `stroke:${LINES[line].color}` }, tf.f.root);
    const lastP = pts[pts.length - 1];
    svg('circle', { class: 'dot', cx: tf.x(v.T), cy: tf.y(lastP.h), r: 4, style: `fill:${LINES[line].color}` }, tf.f.root);
    endLabels.push({ x: tf.x(v.T), y: tf.y(lastP.h), text: `${LINES[line].short} ${lastP.h.toFixed(1)} h` });
  }
  cursorAt(tf, v.T);
  placeLabels(tf.f, endLabels, []);
  timeHover(tf, [], (t, T) => {
    html('div', { class: 't-value' }, t, fmtWhen.format(T));
    for (const line of Object.keys(LINES)) {
      const pts = series[line].filter((p) => p.t <= T);
      const row = html('div', { class: 't-row' }, t);
      const name = html('span', {}, row);
      html('span', { class: 'key', style: `background:${LINES[line].color}` }, name);
      name.appendChild(document.createTextNode(LINES[line].short));
      html('span', {}, row, `${(pts.length ? pts[pts.length - 1].h : 0).toFixed(1)} h`);
    }
  });
  const rows = [];
  for (const line of Object.keys(LINES)) for (const p of series[line].filter((q) => q.t <= v.T)) rows.push([fmtWhen.format(p.t), LINES[line].short, p.s.run, fmtDur(p.s.fit_seconds), `${p.h.toFixed(2)} h`, p.t]);
  rows.sort((a, b) => a[5] - b[5]);
  renderTable($('table-compute'), ['Completed', 'Line', 'Run', 'Fit time', 'Cumulative'], rows.map((r) => r.slice(0, 5)), [3, 4]);
}

// ---------- legend ----------
function drawLegend() {
  const box = $('legend-frontier');
  box.replaceChildren();
  for (const [key, line] of Object.entries(LINES)) {
    const b = html('button', { class: 'item', type: 'button', 'aria-pressed': String(state.lines[key]), title: 'Show or hide this line' }, box);
    const s = svg('svg', { width: 12, height: 12, viewBox: '0 0 12 12' }, b);
    svg('circle', { cx: 6, cy: 6, r: 5, style: `fill:${line.color}` }, s);
    const unscored = !state.data.entries.some((e) => e.line === key && score(e) !== null);
    b.appendChild(document.createTextNode(line.label + (unscored ? ' — no PSIS-LOO scores yet (table only)' : '')));
    b.addEventListener('click', () => { state.lines[key] = !state.lines[key]; render(); });
  }
  const mk = (drawFn, text) => {
    const it = html('span', { class: 'item' }, box);
    const s = svg('svg', { width: 18, height: 12, viewBox: '0 0 18 12' }, it);
    drawFn(s);
    it.appendChild(document.createTextNode(text));
  };
  mk((s) => svg('circle', { cx: 6, cy: 6, r: 4.5, style: 'fill:var(--surface-1);stroke:var(--text-secondary);stroke-width:2' }, s), 'hollow = fails the gate or screen-grade');
  for (const c of state.hws) {
    mk((s) => mark(s, hwShape(c), 6, 6, 4.5, 'var(--text-secondary)', true), hwShort(c));
  }
  for (const c of state.hws) {
    mk((s) => svg('path', { d: 'M1,10 H7 V3 H17', class: 'frontier-line', 'stroke-dasharray': dashOf(c),
      style: 'fill:none;stroke:var(--text-primary);stroke-width:2' }, s), state.hws.length > 1 ? `frontier · ${hwShort(c)}` : 'frontier');
  }
  mk((s) => svg('polygon', { points: '1,2 11,2 6,11', style: 'fill:var(--text-secondary)' }, s), 'below the axis floor');
}

// ---------- KPI tiles ----------
function tile(parent, label, value, small, sub, hero = false) {
  const t = html('div', { class: 'tile' + (hero ? ' hero' : '') }, parent);
  html('div', { class: 'label' }, t, label);
  const v = html('div', { class: 'value' }, t, value);
  if (small) { v.appendChild(document.createTextNode(' ')); html('small', {}, v, small); }
  for (const line of [].concat(sub || [])) html('div', { class: 'sub' }, t, line);
  return t;
}
function drawKpis(v) {
  const box = $('kpis');
  box.replaceChildren();
  const snaps = state.data.snapshots;
  const multi = state.hws.length > 1;
  // One best per selected hardware class (the board rule, per class).
  for (const c of state.hws) {
    const b = v.bests[c];
    const label = multi ? `Best on ${hwShort(c)} (board rule)` : 'Best PSIS-LOO ΔELPD vs baseline (board rule)';
    if (!b) { tile(box, label, '—', null, 'No gate-passing PSIS-scored entry yet', !multi); continue; }
    let prevBest = null;
    for (let i = state.idx; i >= 0; i--) {
      const h = cls(snaps[i], c);
      if (h.best && h.best !== b.key) { prevBest = h; break; }
    }
    const ranked = v.entries.filter((e) => e.hardware_class === c && e.passes && score(e) !== null).sort((p, q) => score(q) - score(p));
    const top = ranked[0];
    const inWindow = ranked.find((e) => e.fit <= FIT_WINDOW);
    tile(box, label, fmtDelta(score(b)), fmtSE(scoreErr(b)), [
      entryLabel(b) + (b.design_text ? ` — ${b.design_text}` : ''),
      `${fmtDur(b.fit)}: the fastest entry within 2 SE of the top score` +
        (top && top.key !== b.key ? ` (top: ${entryLabel(top)}, ${fmtDelta(score(top))}, ${fmtDur(top.fit)})` : ''),
      inWindow ? `Most accurate within 15 min: ${entryLabel(inWindow)} ${fmtDelta(score(inWindow))} (${fmtDur(inWindow.fit)})`
        : 'No passing entry within 15 min',
      prevBest ? `Previous best: ${prevBest.best} (${fmtDelta(prevBest.best_delta)})` : 'First gate-passing entry',
    ], !multi);
  }
  const front = v.entries.filter((e) => e.onFrontier).sort((a, b) => a.fit - b.fit);
  tile(box, 'On the frontier', String(front.length), front.length === 1 ? 'entry' : 'entries',
    state.hws.map((c) => {
      const fc = front.filter((e) => e.hardware_class === c);
      const head = multi ? `${hwShort(c)}: ${fc.length}` : '';
      return fc.length ? `${head}${multi ? ', ' : ''}fastest ${entryLabel(fc[0])} (${fmtDur(fc[0].fit)}), most accurate ${entryLabel(fc[fc.length - 1])}` : `${head}${multi ? ', ' : ''}none`;
    }));
  const passing = v.entries.filter((e) => e.passes).length;
  const byLine = (l) => v.entries.filter((e) => e.line === l).length;
  const psisScored = v.entries.filter((e) => score(e) !== null).length;
  tile(box, 'Entries', String(v.entries.length), null,
    [`${psisScored} PSIS-scored · ${passing} pass the gate`, `${byLine('frontier')} Gibbs · ${byLine('pymc')} PyMC · ${byLine('numpyro')} NumPyro`]);
  const splits = allSplitsCompleted(v.T);
  const hours = splits.reduce((a, { s }) => a + s.fit_seconds, 0) / 3600;
  const cost = v.entries.reduce((a, e) => a + (e.cost_usd || 0), 0);
  tile(box, 'Compute in scored runs', `${hours.toFixed(1)} h`, null,
    [`${splits.length} split runs`, `≈ $${cost.toFixed(0)} Modal list price (per entry, larger split)`]);
}

// ---------- tables ----------
function renderTable(container, headers, rows, numeric = []) {
  container.replaceChildren();
  const table = html('table', {}, container);
  const tr = html('tr', {}, html('thead', {}, table));
  headers.forEach((h, i) => html('th', { class: numeric.includes(i) ? 'num' : null, scope: 'col' }, tr, h));
  const body = html('tbody', {}, table);
  for (const r of rows) {
    const row = html('tr', {}, body);
    r.forEach((c, i) => html('td', { class: numeric.includes(i) ? 'num' : null }, row, c));
  }
}
const COLUMNS = [
  { key: 'entry', label: 'Entry', get: (e) => e.key },
  { key: 'design', label: 'Design', get: (e) => e.design_text || e.design },
  { key: 'psis', label: 'PSIS-LOO ΔELPD', num: true, get: (e) => score(e) ?? -Infinity, fmt: (e) => (e.psis ? `${fmtDelta(score(e))} ${fmtSE(scoreErr(e))}` : '—') },
  { key: 'k', label: 'k over threshold', num: true, get: (e) => (e.psis ? e.psis.k_share : Infinity), fmt: (e) => (e.psis ? `${(100 * e.psis.k_share).toFixed(1)}%` : '—') },
  { key: 'rows', label: 'Held-out ΔELPD', num: true, get: (e) => e.splits.rows?.delta ?? -Infinity, fmt: (e) => `${fmtDelta(e.splits.rows?.delta)} ${fmtSE(e.splits.rows?.delta_se)}` },
  { key: 'units', label: 'Units ΔELPD', num: true, get: (e) => e.splits.units?.delta ?? -Infinity,
    fmt: (e) => (e.splits.units ? `${fmtDelta(e.splits.units.delta)} ${fmtSE(e.splits.units.delta_se)}` : '—') },
  { key: 'fit', label: 'Fit time', num: true, get: (e) => e.fit, fmt: (e) => fmtDur(e.fit) },
  { key: 'timing', label: 'Timing', num: true, get: (e) => e.other_cores ?? Infinity, fmt: timingText },
  { key: 'hardware', label: 'Hardware', get: (e) => e.hardware },
  { key: 'draws', label: 'Chains × draws', num: true, get: (e) => (e.chains || 0) * (e.draws || 0), fmt: drawsText },
  { key: 'gate', label: 'Gate', get: (e) => (e.passes ? 2 : e.grade === 'screen' ? 1 : 0) },
  { key: 'frontier', label: 'Frontier', get: (e) => (e.isBest ? 2 : e.onFrontier ? 1 : 0) },
  { key: 'landed', label: 'Row result landed', num: true, get: (e) => Date.parse(e.available_at), fmt: (e) => fmtWhen.format(Date.parse(e.available_at)) },
];
function drawEntries(v) {
  const box = $('entries-table');
  box.replaceChildren();
  const table = html('table', {}, box);
  const head = html('tr', {}, html('thead', {}, table));
  for (const c of COLUMNS) {
    const th = html('th', { class: c.num ? 'num' : null, scope: 'col',
      'aria-sort': state.sort.key === c.key ? (state.sort.dir > 0 ? 'ascending' : 'descending') : null }, head);
    const b = html('button', { type: 'button' }, th, c.label + (state.sort.key === c.key ? (state.sort.dir > 0 ? ' ↑' : ' ↓') : ''));
    b.addEventListener('click', () => {
      state.sort = { key: c.key, dir: state.sort.key === c.key ? -state.sort.dir : (c.num ? -1 : 1) };
      drawEntries(asOf(state.idx));
    });
  }
  html('th', { scope: 'col' }, head, 'Notes');
  const col = COLUMNS.find((c) => c.key === state.sort.key);
  const rows = visibleEntries(v).sort((a, b) => {
    const x = col.get(a), y = col.get(b);
    return (x < y ? -1 : x > y ? 1 : 0) * state.sort.dir;
  });
  const body = html('tbody', {}, table);
  for (const e of rows) {
    const tr = html('tr', { class: e.isBest ? 'best' : null }, body);
    for (const c of COLUMNS) {
      const td = html('td', { class: c.num ? 'num' : null }, tr);
      if (c.key === 'entry') {
        html('span', { class: 'swatch' + (e.passes ? '' : ' hollow'), style: e.passes ? `background:${LINES[e.line].color}` : `color:${LINES[e.line].color}`, 'aria-hidden': 'true' }, td);
        td.appendChild(document.createTextNode(e.key));
      } else if (c.key === 'gate') {
        const kind = e.passes ? 'good' : e.grade === 'screen' ? 'screen' : 'bad';
        const span = html('span', { class: `status ${kind}` }, td);
        html('span', { class: 'icon', 'aria-hidden': 'true' }, span, e.passes ? '✓' : e.grade === 'screen' ? '◐' : '✕');
        span.appendChild(document.createTextNode(gateText(e)));
      } else if (c.key === 'frontier') {
        td.textContent = e.isBest ? 'best' + (e.onFrontier ? ', frontier' : '') : e.onFrontier ? 'frontier' : '';
      } else {
        td.textContent = c.fmt ? c.fmt(e) : c.get(e);
      }
    }
    const notes = html('td', {}, tr);
    const lines = [e.note, ...(e.annotations || [])].filter(Boolean);
    if (lines.length) {
      const det = html('details', {}, notes);
      html('summary', {}, det, `${lines.length} note${lines.length > 1 ? 's' : ''}`);
      const ul = html('ul', {}, det);
      for (const l of lines) html('li', {}, ul, l);
    }
  }
  $('entries-caption').textContent = `${rows.length} of ${v.entries.length} entries scored by ${fmtWhen.format(v.T)} (filters apply). ` +
    'An entry is one design × feature set × commit; its row and unit splits are separate runs. Click a header to sort.';
}

function drawMilestones(v) {
  const box = $('milestones');
  box.replaceChildren();
  for (const m of [...state.data.milestones].reverse()) {
    const li = html('li', { class: Date.parse(m.at) > v.T ? 'future' : null }, box);
    html('span', { class: 'when' }, li, fmtWhen.format(Date.parse(m.at)));
    html('span', { class: `kind ${m.kind}` }, li, m.kind === 'selection' ? 'App model' : `PR #${m.pr}`);
    const what = html('span', { class: 'what' }, li, m.title);
    if (m.model) html('small', {}, what, m.model);
  }
}

// ---------- top-level ----------
function setIdx(i) {
  state.idx = Math.max(0, Math.min(state.data.snapshots.length - 1, i));
  $('asof-range').value = String(state.idx);
  render();
}
function render() {
  const v = asOf(state.idx);
  const dom = domains();
  $('asof-label').value = fmtWhen.format(v.T) + (state.idx === state.data.snapshots.length - 1 ? ' (latest)' : '');
  drawLegend();
  drawKpis(v);
  drawFrontier(v, dom);
  drawImplementations(v);
  drawUnits(v, dom);
  drawValidation(v, dom);
  drawVariance(v);
  drawCompute(v, dom);
  drawProgress(v, dom);
  drawFitTime(v, dom);
  drawEntries(v);
  drawMilestones(v);
}

function initTheme() {
  const saved = localStorage.getItem('dashboard-theme');
  if (saved) document.documentElement.dataset.theme = saved;
  const btn = $('theme');
  const isDark = () => (document.documentElement.dataset.theme || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')) === 'dark';
  const label = () => { btn.textContent = isDark() ? 'Light mode' : 'Dark mode'; };
  label();
  btn.addEventListener('click', () => {
    const next = isDark() ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    localStorage.setItem('dashboard-theme', next);
    label();
    document.body.style.background = next === 'dark' ? '#0d0d0d' : '#f9f9f7';
  });
  if (isDark()) document.body.style.background = '#0d0d0d';
}

async function main() {
  tip.el = $('tooltip');
  initTheme();
  const res = await fetch('data.json', { cache: 'no-store' });
  state.data = await res.json();
  const tz = state.data.timezone;
  fmtWhen = new Intl.DateTimeFormat('en-US', { timeZone: tz, month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
  fmtDay = new Intl.DateTimeFormat('en-US', { timeZone: tz, month: 'short', day: 'numeric' });
  fmtHour = new Intl.DateTimeFormat('en-US', { timeZone: tz, hour: 'numeric', hourCycle: 'h23' });
  const d = state.data;
  $('build-meta').textContent = `Built ${fmtWhen.format(Date.parse(d.generated_at))} from commit ${d.builder_commit}${d.builder_dirty ? ' (uncommitted changes)' : ''}`;
  const foot = $('footer');
  for (const text of [
    ...d.footer,
    'Gate: split R-hat < 1.01 and bulk ESS > 400; frontier-line runs also need R-hat < 1.05 over every group effect (1.1 when recomputed from older runs\' kept draws), and NUTS runs need no divergences. PyMC screens that fail it are screen-grade: shown, never best or on the frontier.',
    'Fit times compare well within a line but only roughly across lines: PyMC screens are 4 chains × 1,000/1,000 on CPU; frontier-line runs are production-length on Modal GPUs. The board is docs/model/leaderboard/leaderboard.md; this page applies the same rules at every date.',
  ]) html('p', {}, foot, text);

  const classes = {};
  for (const e of d.entries) {
    classes[e.hardware_class] = classes[e.hardware_class] || { n: 0, scored: 0 };
    classes[e.hardware_class].n += 1;
    if (e.psis) classes[e.hardware_class].scored += 1;
  }
  const order = Object.keys(classes).sort((a, b) => classes[b].scored - classes[a].scored || a.localeCompare(b));
  // Default: every thelio class (the target hardware); the choice is remembered.
  const thelio = order.filter((c) => c.startsWith('thelio'));
  let saved = [];
  try { saved = JSON.parse(localStorage.getItem('dashboard-hw') || '[]'); } catch { saved = []; }
  saved = saved.filter((c) => classes[c]);
  state.hws = saved.length ? saved : thelio.length ? thelio : order.slice(0, 1);
  const box = $('hw-select');
  const boxes = {};
  const apply = (list) => {
    state.hws = order.filter((c) => list.includes(c));
    for (const c of order) boxes[c].checked = state.hws.includes(c);
    localStorage.setItem('dashboard-hw', JSON.stringify(state.hws));
    render();
  };
  for (const c of order) {
    const lab = html('label', { class: 'check chip' }, box);
    boxes[c] = html('input', { type: 'checkbox' }, lab);
    boxes[c].checked = state.hws.includes(c);
    const s = svg('svg', { width: 14, height: 14, viewBox: '0 0 14 14', 'aria-hidden': 'true' }, lab);
    mark(s, hwShape(c), 7, 7, 4.5, 'var(--text-secondary)', true);
    lab.appendChild(document.createTextNode(`${c} (${classes[c].scored} PSIS-scored of ${classes[c].n})`));
    boxes[c].addEventListener('change', () => {
      const next = order.filter((k) => boxes[k].checked);
      apply(next.length ? next : [c]); // keep at least one class selected
    });
  }
  const quick = (text, list) => {
    const b = html('button', { class: 'ghost', type: 'button' }, box, text);
    b.addEventListener('click', () => apply(list));
  };
  if (thelio.length > 1) quick('All thelio', thelio);
  quick('All', order);
  state.hws = order.filter((c) => state.hws.includes(c));
  const range = $('asof-range');
  range.max = String(d.snapshots.length - 1);
  state.idx = d.snapshots.length - 1;
  range.value = String(state.idx);
  range.addEventListener('input', () => setIdx(Number(range.value)));
  $('asof-prev').addEventListener('click', () => setIdx(state.idx - 1));
  $('asof-next').addEventListener('click', () => setIdx(state.idx + 1));
  $('asof-now').addEventListener('click', () => setIdx(d.snapshots.length - 1));
  $('asof-play').addEventListener('click', () => {
    const btn = $('asof-play');
    if (state.playing) { clearInterval(state.playing); state.playing = null; btn.textContent = 'Play'; return; }
    if (state.idx >= d.snapshots.length - 1) setIdx(0);
    btn.textContent = 'Pause';
    state.playing = setInterval(() => {
      if (state.idx >= d.snapshots.length - 1) { clearInterval(state.playing); state.playing = null; btn.textContent = 'Play'; return; }
      setIdx(state.idx + 1);
    }, 350);
  });
  for (const [id, key] of [['show-failed', 'showFailed'], ['show-se', 'showSE'], ['full-range', 'fullRange']]) {
    $(id).addEventListener('change', (evt) => { state[key] = evt.target.checked; render(); });
  }
  for (const b of document.querySelectorAll('.table-toggle')) {
    b.addEventListener('click', () => {
      const chart = $(`chart-${b.dataset.target}`), table = $(`table-${b.dataset.target}`);
      const toTable = table.hidden;
      table.hidden = !toTable;
      chart.hidden = toTable;
      b.textContent = toTable ? 'Chart view' : 'Table view';
      if (!toTable) render();
    });
  }
  // Re-render on width changes only (height follows the content).
  let pending = null, lastWidth = 0;
  new ResizeObserver((items) => {
    const w = Math.round(items[0].contentRect.width);
    if (w === lastWidth) return;
    lastWidth = w;
    clearTimeout(pending);
    pending = setTimeout(render, 120);
  }).observe(document.querySelector('.viz-root'));
  render();
}

main().catch((err) => {
  const p = document.createElement('p');
  p.textContent = `Could not load the dashboard data: ${err}`;
  document.querySelector('.viz-root').prepend(p);
});

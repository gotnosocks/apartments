const D = JSON.parse(document.getElementById('data').textContent);
const C = (() => { const s = getComputedStyle(document.documentElement); const g = n => s.getPropertyValue(n).trim();
  return { bg: g('--panel'), fg: g('--fg'), mu: g('--muted'), gr: g('--grid'), blue: g('--blue'), brown: g('--brown'), yel: g('--yellow'), teal: g('--teal'), red: g('--red'), pink: g('--pink') }; })();
const T = Object.fromEntries(D.terms.map(t => [t.k, t]));
const usd = v => '$' + Math.round(v).toLocaleString('en-US');
const pct = v => (v >= 0 ? '+' : '') + ((Math.exp(v) - 1) * 100).toFixed(Math.abs(v) < 0.05 ? 1 : 0) + '%';
const lp = v => (v >= 0 ? '+' : '−') + Math.abs(v).toFixed(3);
const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
document.getElementById('run').textContent = D.run;

// table
const tb = document.querySelector('#tt tbody');
D.terms.filter(t => t.k !== 'market').sort((a, b) => Math.abs(b.f[2]) - Math.abs(a.f[2])).forEach(t => {
  const tr = document.createElement('tr');
  const cells = [[t.lab], [t.ex, 'm'], [lp(t.f[2]), 'n'], [t.f[0] === t.f[4] ? '' : lp(t.f[0]) + ' to ' + lp(t.f[4]), 'n'], ['×' + Math.exp(t.f[2]).toFixed(3), 'n'], [lp(t.df[2]), 'n']];
  cells.forEach(([v, c]) => { const td = document.createElement('td'); td.textContent = v; if (c) td.className = c; tr.appendChild(td); });
  tb.appendChild(tr);
});

// groups for the build-up
const G = [
  { name: 'Market, April 2025', keys: ['market'], col: C.mu },
  { name: 'Five bedrooms', keys: ['bedrooms'], col: C.blue },
  { name: 'Three baths', keys: ['bathrooms'], col: C.blue },
  { name: 'Tribeca', keys: ['neighbourhood'], col: C.teal },
  { name: 'Building’s own level and walk', keys: ['building', 'building_drift', 'building_feature_slopes'], col: C.brown },
  { name: 'Building facts', keys: ['building size', 'building status', 'building era'], col: C.teal },
  { name: 'Small unit features', keys: ['rooms beyond bedrooms', 'floor', 'description', 'relisting', 'elevator', 'doorman', 'hvac', 'views', 'bedroom_market_curve'], col: C.blue },
  { name: 'Unit’s own effect', keys: ['unit'], col: C.pink },
];
G.forEach(g => {
  const n = 200; const dr = new Array(n).fill(0);
  g.keys.forEach(k => { const t = T[k]; for (let i = 0; i < n; i++) dr[i] += t.dr.length ? t.dr[i] : t.f[2]; });
  const s = dr.slice().sort((a, b) => a - b);
  g.med = g.keys.reduce((a, k) => a + T[k].f[2], 0);
  g.lo = s[4]; g.hi = s[195];
});
let cum = 0; G.forEach(g => { g.from = cum; cum += g.med; g.to = cum; });

// canvas
const cv = document.getElementById('cv'); const ctx = cv.getContext('2d');
let W = 0, H = 0;
function size() { const r = cv.getBoundingClientRect(); const dpr = devicePixelRatio || 1; W = r.width; H = W < 560 ? 480 : Math.max(340, Math.min(560, W * 0.58));
  cv.style.height = H + 'px'; cv.width = W * dpr; cv.height = H * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0); }
const F = (px, w = 400, fam = 'sans') => `${w} ${px}px ${fam === 'serif' ? '"Source Serif 4", Georgia, serif' : '"Source Sans 3", Helvetica, Arial, sans-serif'}`;
function text(s, x, y, o = {}) { ctx.font = F(o.px || 13, o.w || 400, o.fam); ctx.fillStyle = o.c || C.fg; ctx.textAlign = o.a || 'left'; ctx.textBaseline = o.b || 'middle'; ctx.globalAlpha = o.al ?? 1; ctx.fillText(s, x, y); ctx.globalAlpha = 1; }
function line(x1, y1, x2, y2, c, w = 1, dash) { ctx.strokeStyle = c; ctx.lineWidth = w; ctx.setLineDash(dash || []); ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke(); ctx.setLineDash([]); }
function rect(x, y, w, h, c, al = 1) { ctx.globalAlpha = al; ctx.fillStyle = c; ctx.fillRect(x, y, w, h); ctx.globalAlpha = 1; }
function dot(x, y, r, c, al = 1) { ctx.globalAlpha = al; ctx.fillStyle = c; ctx.beginPath(); ctx.arc(x, y, r, 0, 7); ctx.fill(); ctx.globalAlpha = 1; }
const narrow = () => W < 560;
const PAD = () => ({ l: narrow() ? 12 : 24, r: narrow() ? 12 : 24, t: 46, b: 40 });
function title(s) { text(s, PAD().l, 24, { px: narrow() ? 17 : 20, fam: 'serif', w: 500 }); }

// scene: the listing
function sceneAd(step, k) {
  const p = PAD(); title('The listing, as StreetEasy recorded it');
  const days = [['Apr 29', 0, 'Drafted at $12,500'], ['Apr 30', 1, 'Goes live'], ['May 5', 6, 'In contract; ask raised to $13,500'], ['May 8', 9, 'Active again'], ['May 13', 14, 'Rented, no price given']];
  const x0 = p.l + 20, x1 = W - p.r - 20, sx = d => x0 + (x1 - x0) * d / 14;
  const ys = narrow() ? H * 0.5 : H * 0.62, yp = d => d < 6 ? 12500 : 13500;
  const py = v => ys - 40 - (v - 12000) / 2000 * (H * 0.36);
  line(x0, ys, x1, ys, C.gr, 2);
  const shown = step === 0 ? 2 : 5;
  days.slice(0, shown).forEach(([lab, d, what], i) => {
    const x = sx(d); dot(x, ys, 5, i === 2 ? C.yel : C.fg, k);
    if (!narrow()) text(lab, x, ys + 18, { a: 'center', c: C.mu, px: 12, al: k });
    const below = i % 2 === 0;
    if (narrow()) text(lab + '  ' + what, p.l, ys + 44 + i * 20, { px: 13, al: k });
    else text(what, Math.min(Math.max(x, p.l + 60), W - p.r - 60), ys + (below ? 40 : 58), { a: 'center', px: 13, al: k });
  });
  // price steps
  const end = step === 0 ? 1 : 14;
  ctx.strokeStyle = C.yel; ctx.lineWidth = 2.5; ctx.beginPath(); ctx.moveTo(sx(0), py(12500));
  const e = Math.min(end, 0 + (end) * k);
  ctx.lineTo(sx(Math.min(e, 6)), py(12500)); if (e > 6) { ctx.lineTo(sx(6), py(13500)); ctx.lineTo(sx(e), py(13500)); } ctx.stroke();
  text('$12,500', sx(0), py(12500) - 14, { c: C.yel, w: 600 });
  if (step > 0) { text('$13,500  (+8%)', sx(6) + 6, py(13500) - 14, { c: C.yel, w: 600, al: k }); text('the price the model fits', sx(6) + 6, py(13500) + 14, { c: C.mu, px: 12, al: k }); }
}

// scene: build-up (waterfall on a log dollar axis)
function axisLog(lo, hi, x0, x1, y, ticks) {
  const sx = v => x0 + (Math.log(v) - Math.log(lo)) / (Math.log(hi) - Math.log(lo)) * (x1 - x0);
  ticks.forEach(t => { const x = sx(t); line(x, 56, x, y, C.gr, 1); text(t >= 1000 ? '$' + (t / 1000) + 'k' : '$' + t, x, y + 14, { a: 'center', c: C.mu, px: 12 }); });
  return sx;
}
function sceneBuild(step, k) {
  const p = PAD(); title('Start from the market, then multiply');
  const lab = narrow() ? 0 : 210;
  const x0 = p.l + lab, x1 = W - p.r - (narrow() ? 8 : 70), yb = H - p.b;
  const sx = axisLog(3000, 18000, x0, x1, yb, [3000, 4000, 6000, 8000, 10000, 13500, 18000]);
  const rows = G.length + 1, rh = (yb - 64) / rows;
  const shown = Math.min(G.length, step + 1);
  for (let i = 0; i < shown; i++) {
    const g = G[i], y = 64 + i * rh + rh / 2, a = i === shown - 1 ? k : 1;
    const xa = sx(Math.exp(D.market.offset + (i === 0 ? -3 : 0) + g.from)) , xb = sx(Math.exp(g.from + (i === 0 ? 0 : 0)));
    const from = i === 0 ? sx(3000) : sx(Math.exp(g.from)); const to = sx(Math.exp(g.from + (g.to - g.from) * a));
    const hh = Math.max(8, rh * 0.5);
    rect(Math.min(from, to), y - hh / 2, Math.abs(to - from) || 2, hh, g.col, 0.85);
    if (i > 0) { // 95% range of this group's contribution, drawn at the bar's end
      const lo = sx(Math.exp(g.from + g.lo)), hi = sx(Math.exp(g.from + g.hi));
      line(lo, y, hi, y, C.fg, 1.5); line(lo, y - 5, lo, y + 5, C.fg, 1.5); line(hi, y - 5, hi, y + 5, C.fg, 1.5);
      line(from, y + hh / 2, from, y - rh / 2 - hh / 2 + rh, C.gr, 1, [3, 3]);
    }
    const nm = g.name + (i === 0 ? '  ' + usd(Math.exp(g.to)) : '  ' + pct(g.med));
    if (narrow()) text(nm, p.l, y - hh / 2 - 8, { px: 12, al: a, c: C.fg });
    else { text(g.name, x0 - 10, y, { a: 'right', px: 13, al: a }); text(i === 0 ? usd(Math.exp(g.to)) : pct(g.med), Math.max(from, to) + 8, y - (i > 0 ? 12 : 0), { px: 12, c: C.mu, al: a }); }
  }
  if (step >= G.length - 1) {
    const y = 64 + G.length * rh + rh / 2, f = D.fitted;
    const lo = sx(f.p2_5), hi = sx(f.p97_5), m = sx(f.p50);
    rect(lo, y - 7, hi - lo, 14, C.yel, 0.35 * k); line(m, y - 11, m, y + 11, C.yel, 3);
    const ax = sx(13500); line(ax, 56, ax, yb, C.red, 1.5, [5, 4]);
    text('ask $13,500', ax + 4, 56, { c: C.red, px: 12, w: 600 });
    if (narrow()) text('Fitted rent ' + usd(f.p50) + '  (95% ' + usd(f.p2_5) + '–' + usd(f.p97_5) + ')', p.l, y - 18, { px: 12, w: 600, c: C.yel, al: k });
    else { text('Fitted rent', x0 - 10, y, { a: 'right', w: 600, c: C.yel, al: k }); text(usd(f.p50), m, y + 22, { a: 'center', c: C.yel, w: 600, al: k }); }
  }
}

// scene: uncertainty strips
const STRIP = ['bedrooms', 'bathrooms', 'neighbourhood', 'building_drift', 'building', 'unit', 'building_feature_slopes', 'building status', 'building size', 'building era', 'elevator'];
function sceneStrips(step, k) {
  const p = PAD(); title(step === 0 ? 'How sure is each piece?' : 'Two chains, one answer');
  const lab = narrow() ? 0 : 200, x0 = p.l + lab, x1 = W - p.r, yb = H - p.b;
  const lo = -0.32, hi = 0.66, sx = v => x0 + (v - lo) / (hi - lo) * (x1 - x0);
  [-0.3, -0.2, -0.1, 0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6].forEach(v => { line(sx(v), 56, sx(v), yb, v === 0 ? C.mu : C.gr, 1); if (!narrow() || Math.round(v * 10) % 2 === 0) text(v.toFixed(1), sx(v), yb + 14, { a: 'center', px: 12, c: C.mu }); });
  text('log points', x1, yb + 30, { a: 'right', px: 11, c: C.mu });
  const rh = (yb - 64) / STRIP.length;
  STRIP.forEach((key, i) => {
    const t = T[key], y = 64 + i * rh + rh / 2;
    if (narrow()) text(t.lab, p.l, y - rh * 0.32, { px: 11, c: C.mu }); else text(t.lab, x0 - 10, y, { a: 'right', px: 13 });
    const dr = t.dr.length ? t.dr : [t.f[2]];
    dr.forEach((v, j) => { const ch = j < dr.length / 2 ? 0 : 1; const jit = ((j * 7919) % 97) / 97 - 0.5;
      const yy = step === 0 ? y + jit * rh * 0.5 : y + (ch ? 1 : -1) * rh * 0.16 + jit * rh * 0.22;
      dot(sx(v), yy, 1.7, step === 0 ? C.blue : (ch ? C.teal : C.brown), 0.55 * k); });
    if (step === 1 && t.cm) t.cm.forEach((m, ch) => line(sx(m), y - rh * 0.4, sx(m), y + rh * 0.4, ch ? C.teal : C.brown, 2.5));
    if (step === 0) { line(sx(t.f[0]), y + rh * 0.36, sx(t.f[4]), y + rh * 0.36, C.yel, 1.5); }
  });
  if (step === 1) { text('chain 1', W - p.r - 64, 40, { c: C.brown, w: 600, px: 12 }); text('chain 2', W - p.r, 40, { c: C.teal, w: 600, px: 12, a: 'right' }); }
}

// scene: against typical
const DIFF = ['bedrooms', 'neighbourhood', 'bathrooms', 'building_drift', 'building', 'unit', 'size', 'building size', 'building status', 'building_feature_slopes', 'building era', 'laundry'];
function sceneDiff(step, k) {
  const p = PAD(); title('Against a typical Manhattan one-bedroom');
  const lab = narrow() ? 0 : 200, x0 = p.l + lab, x1 = W - p.r - 40, yb = H - p.b;
  const lo = -0.3, hi = 0.65, sx = v => x0 + (v - lo) / (hi - lo) * (x1 - x0);
  [-0.2, 0, 0.2, 0.4, 0.6].forEach(v => { line(sx(v), 56, sx(v), yb, v === 0 ? C.mu : C.gr, 1); text((v >= 0 ? '×' : '×') + Math.exp(v).toFixed(2), sx(v), yb + 14, { a: 'center', px: 12, c: C.mu }); });
  const rh = (yb - 64) / DIFF.length;
  DIFF.forEach((key, i) => {
    const t = T[key], y = 64 + i * rh + rh / 2, v = step === 0 ? t.f[2] : t.df[2];
    const prev = t.f[2], cur = prev + (v - prev) * (step === 0 ? 1 : k);
    if (narrow()) text(t.lab, p.l, y - rh * 0.32, { px: 11, c: C.mu }); else text(t.lab, x0 - 10, y, { a: 'right', px: 13 });
    const hh = Math.max(6, rh * 0.42);
    rect(Math.min(sx(0), sx(cur)), y - hh / 2, Math.abs(sx(cur) - sx(0)), hh, cur >= 0 ? C.teal : C.brown, 0.85);
    if (step === 1 && key === 'neighbourhood' && !narrow()) text('Tribeca +0.232, East Village −0.136', sx(cur) + 6, y, { px: 12, c: C.mu, al: k });
  });
  text(step === 0 ? '5S alone' : '5S minus the 379 E 10th St row', x1 + 40, 40, { a: 'right', px: 12, c: C.mu });
}

// scene: predictive
function hist(vals, sx, x0, x1, yb, hmax, col, al, bins = 46, lo = 9000, hi = 19000) {
  const n = new Array(bins).fill(0); vals.forEach(v => { const b = Math.floor((v - lo) / (hi - lo) * bins); if (b >= 0 && b < bins) n[b]++; });
  const m = Math.max(...n); n.forEach((c, b) => { const xa = sx(lo + (hi - lo) * b / bins), xb = sx(lo + (hi - lo) * (b + 1) / bins); rect(xa + 0.5, yb - c / m * hmax, xb - xa - 1, c / m * hmax, col, al); });
}
function sceneTail(step, k) {
  const p = PAD(); title(['The fitted rent is the centre, not the ask', 'Add the noise of a single ad', 'Leave 5S out of the fit'][step]);
  const x0 = p.l + 10, x1 = W - p.r - 10, yb = H - p.b - 96, lo = 9000, hi = 19000;
  const sx = v => x0 + (v - lo) / (hi - lo) * (x1 - x0);
  [10000, 12000, 14000, 16000, 18000].forEach(v => { line(sx(v), 56, sx(v), yb, C.gr, 1); text(usd(v), sx(v), yb + 14, { a: 'center', px: 12, c: C.mu }); });
  const hmax = yb - 80;
  if (step === 0) hist(D.total.dr.map(Math.exp), sx, x0, x1, yb, hmax * k, C.yel, 0.8, 120);
  else hist(D.pins, sx, x0, x1, yb, hmax, C.blue, step === 1 ? 0.8 * k : 0.35);
  const ask = sx(13500); line(ask, 56, ask, yb, C.red, 2, [5, 4]); text('ask $13,500', ask + 5, 62, { c: C.red, w: 600, px: 12 });
  const band = (y, q, col, name, al) => { const [a, b, c, d, m] = q; line(sx(a), y, sx(d), y, col, 2); rect(sx(b), y - 5, sx(c) - sx(b), 10, col, 0.9); line(sx(m), y - 9, sx(m), y + 9, C.fg, 2);
    text(name, narrow() ? sx(d) + 6 : sx(d) + 8, y, { px: 12, c: col, w: 600, al }); };
  const f = D.fitted, s = D.pred.in_sample, l = D.pred.psis_loo_bundle;
  band(yb + 40, [f.p2_5, f.p10, f.p90, f.p97_5, f.p50], C.yel, narrow() ? 'fitted' : 'fitted rent', 1);
  if (step >= 1) band(yb + 66, [s.p2_5, s.p10, s.p90, s.p97_5, s.median], C.blue, narrow() ? 'in sample' : 'one ad, in sample', k);
  if (step === 2) band(yb + 92, [l.p2_5, l.p10, l.p90, l.p97_5, l.median], C.teal, narrow() ? 'left out' : 'left out (site)', k);
}

// scene: over time
function scenePath(step, k) {
  const p = PAD(); title(step === 0 ? 'The same apartment, priced every month' : 'Against what the building’s 5-beds asked');
  const x0 = p.l + 46, x1 = W - p.r, y0 = 56, yb = H - p.b;
  const t0 = Date.UTC(2014, 0, 1), t1 = Date.UTC(2026, 11, 1);
  const tx = s => { const [y, m, d] = s.split('-').map(Number); return x0 + (Date.UTC(y, m - 1, d || 1) - t0) / (t1 - t0) * (x1 - x0); };
  const lo = 6000, hi = 18500, sy = v => yb - (v - lo) / (hi - lo) * (yb - y0);
  for (let v = 6000; v <= 18000; v += 2000) { line(x0, sy(v), x1, sy(v), C.gr, 1); text('$' + v / 1000 + 'k', x0 - 6, sy(v), { a: 'right', px: 12, c: C.mu }); }
  for (let y = 2014; y <= 2026; y += narrow() ? 3 : 2) text(String(y), tx(y + '-01-01'), yb + 14, { a: 'center', px: 12, c: C.mu });
  const P = D.path, n = Math.max(2, Math.round(P.length * (step === 0 ? k : 1)));
  const area = (i0, i1, col, al) => { ctx.globalAlpha = al; ctx.fillStyle = col; ctx.beginPath(); P.slice(0, n).forEach((r, i) => { const x = tx(r[0]); i ? ctx.lineTo(x, sy(r[i1])) : ctx.moveTo(x, sy(r[i1])); });
    P.slice(0, n).reverse().forEach(r => ctx.lineTo(tx(r[0]), sy(r[i0]))); ctx.closePath(); ctx.fill(); ctx.globalAlpha = 1; };
  area(1, 5, C.blue, 0.16); area(2, 4, C.blue, 0.28);
  ctx.strokeStyle = C.blue; ctx.lineWidth = 2; ctx.beginPath(); P.slice(0, n).forEach((r, i) => { i ? ctx.lineTo(tx(r[0]), sy(r[3])) : ctx.moveTo(tx(r[0]), sy(r[3])); }); ctx.stroke();
  if (step >= 1) {
    D.bl.filter(b => b[3] === 5 && b[1]).forEach(b => { const me = b[0] === '#5S'; dot(tx(b[1]), sy(b[2]), me ? 6 : 4, me ? C.yel : C.fg, k); if (me) text('5S $13,500', tx(b[1]) - 8, sy(b[2]) - 14, { a: 'right', c: C.yel, w: 600, px: 12, al: k }); });
    D.comps.filter(c => c[3] === 5).forEach(c => { const x = tx(c[1]), y = sy(c[2]); line(x - 4, y - 4, x + 4, y + 4, C.teal, 1.5); line(x - 4, y + 4, x + 4, y - 4, C.teal, 1.5); });
    text('● this building’s 5-beds   × other Tribeca 5-beds', x0 + 6, y0 + 4, { px: 12, c: C.mu, al: k });
  }
}

const SC = [
  { name: 'The ad', draw: sceneAd, caps: [
    'Unit 5S went up on StreetEasy on <b>30 April 2025</b> at <b>$12,500</b>: 5 bedrooms, 3 baths, 2,000 sq ft, 9 rooms, no fee.',
    'Five days later it went <b>into contract</b> and the ask rose to <b>$13,500</b> the same morning. It rented on 13 May with no price recorded. The model treats the last ask as the closing price, so it explains $13,500.'] },
  { name: 'Build-up', draw: sceneBuild, caps: [
    'The model works in log rent, so each term multiplies. It starts from the <b>market</b>: intercept, 12-year trend and season at the ask date give <b>$4,687</b> for a plain one-bedroom in the reference neighbourhood.',
    '<b>Five or more bedrooms</b> is the biggest single factor: <b>×1.82</b>, taking it past $8,500. The whisker is the term’s 95% range; it is tight because thousands of big units pin it.',
    '<b>Three full baths</b> adds another <b>31%</b>.',
    '<b>Tribeca</b> sits 26% above Chelsea, the reference neighbourhood. That alone puts the unit near $15,000.',
    'Then the <b>building’s own terms</b> pull back about <b>15%</b>. With 13 ads in 12 years they are the widest pieces here, and their 95% range runs from −25% to +6%.',
    '<b>Measured building facts</b> add back about 10%: the historic district (+4%), the 1938 era (+3%) and its small, roomy, low-rise shape (+3%).',
    'The <b>small unit features</b> roughly cancel: nine rooms +2%, the 5th floor and the ad text +2%, a blank elevator field −1%, the big-unit market curve −1%.',
    'Last, the <b>unit’s own effect</b>, learned from its one listing, is close to zero (+0.6%). The product lands at a <b>fitted rent of $13,453</b>, 95% $12,505 to $14,388, right on the $13,500 ask.'] },
  { name: 'Uncertainty', draw: sceneStrips, caps: [
    'Each dot is one of 200 posterior draws for a term. The <b>layout terms</b> (bedrooms, baths, Tribeca) are pinned down to a hundredth of a log point. The building’s level and walk spread across <b>a quarter of a log point</b> and both cross zero.',
    'Split by chain, the two clouds sit on top of each other. Every term’s chain medians are within its posterior sd; the largest gap, on the unit effect, is about <b>0.1 sd</b>. <b>No chain disagreement</b> to mark.'] },
  { name: 'Vs typical', draw: sceneDiff, caps: [
    'Here are 5S’s own terms. To see what makes it expensive rather than what the model’s reference point is, compare it with a typical apartment.',
    'Against the <b>median Manhattan row</b> of April 2025, a one-bedroom at 379 East 10th Street fitted at <b>$4,559</b>, Tribeca’s gap grows to <b>+0.368</b> because the East Village sits below Chelsea. Bedrooms, baths and location explain the whole ×2.95 gap; the building terms take some back.'] },
  { name: 'Prediction', draw: sceneTail, caps: [
    'The yellow histogram is the <b>fitted rent</b>: the model’s centre for this unit, $13,453. It is narrow because it leaves out the scatter of individual ads.',
    'A single ask scatters around that centre with fat-tailed noise (scale 3.3%, 2.2 degrees of freedom). The <b>predicted ask</b> has median <b>$13,449</b>, 80% from $12,442 to $14,492. $13,500 falls at the 53rd percentile.',
    'The honest check leaves 5S out. The site’s PSIS-LOO gives median <b>$13,257</b>, 80% <b>$11,834 to $14,745</b>, 95% $10,963 to $15,875. The real ask sits at the <b>59th percentile</b>: an ordinary result.'] },
  { name: 'Over time', draw: scenePath, caps: [
    'Holding the unit fixed and moving only the market, the big-unit curve, the building’s walk and the season, the model would have priced 5S at about $10,200 in 2014, $13,400 in April 2025 and <b>$14,100 today</b>.',
    'The building’s other 5-beds asked $9,000 to $10,000 in 2014–19, then $13,000 (2N, 2024), $12,500 (6S, Dec 2024) and $14,000 (6S, May 2026). Nearby Tribeca 5-beds asked $12,500 to $15,000. 5S’s $13,500 sits inside the band.'] },
];

const chips = document.getElementById('chips'); let si = 0, st = 0, t0 = 0, raf = 0;
SC.forEach((s, i) => { const b = document.createElement('button'); b.className = 'chip'; b.type = 'button'; b.textContent = s.name; b.onclick = () => go(i, 0); chips.appendChild(b); });
const total = SC.reduce((a, s) => a + s.caps.length, 0);
function flat() { let n = 0; for (let i = 0; i < si; i++) n += SC[i].caps.length; return n + st; }
function go(i, j) { si = i; st = j; t0 = performance.now(); [...chips.children].forEach((c, k) => c.setAttribute('aria-current', k === si)); 
  document.getElementById('caption').innerHTML = SC[si].caps[st]; const f = flat();
  document.getElementById('count').textContent = (f + 1) + ' / ' + total;
  document.getElementById('prev').disabled = f === 0; document.getElementById('next').disabled = f === total - 1;
  try { localStorage.setItem('c165', JSON.stringify([si, st])); } catch (e) {}
  cancelAnimationFrame(raf); raf = requestAnimationFrame(frame); }
function step(d) { let i = si, j = st + d; if (j >= SC[i].caps.length) { i++; j = 0; } if (j < 0) { i--; if (i < 0) return; j = SC[i].caps.length - 1; } if (i >= SC.length) return; go(i, j); }
function frame(now) { const k = reduce ? 1 : Math.min(1, (now - t0) / 700); const e = 1 - Math.pow(1 - k, 3);
  ctx.clearRect(0, 0, W, H); ctx.fillStyle = C.bg; ctx.fillRect(0, 0, W, H); SC[si].draw(st, e); if (k < 1) raf = requestAnimationFrame(frame); }
document.getElementById('prev').onclick = () => step(-1); document.getElementById('next').onclick = () => step(1);
cv.onclick = e => step(e.offsetX < W * 0.25 ? -1 : 1);
addEventListener('keydown', e => { if (e.key === 'ArrowRight') step(1); if (e.key === 'ArrowLeft') step(-1); });
addEventListener('resize', () => { size(); t0 = 0; frame(performance.now()); });
size(); let init = [0, 0]; try { const v = JSON.parse(localStorage.getItem('c165')); if (Array.isArray(v) && SC[v[0]] && SC[v[0]].caps[v[1]]) init = v; } catch (e) {}
go(init[0], init[1]);
document.fonts && document.fonts.ready.then(() => { t0 = 0; frame(performance.now()); });

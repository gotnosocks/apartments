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

// the unit's ads
const lt = document.querySelector('#lt tbody');
D.bl.forEach(b => {
  const asks = b[5].length > 1 ? usd(b[5][0][1]) + ' to ' + usd(b[2]) + ' (' + (b[5].length - 1) + ' cuts)' : usd(b[2]);
  const cells = [[b[0]], [b[1] + ' to ' + b[6], 'm'], [asks, 'n'], [b[4] === 'psis' ? 'in fit' : 'held out', 'm'], [usd(b[7]), 'n'], [Math.round(b[8] * 100) + '%', 'n']];
  const tr = document.createElement('tr');
  cells.forEach(([v, c]) => { const td = document.createElement('td'); td.textContent = v; if (c) td.className = c; tr.appendChild(td); });
  lt.appendChild(tr);
});

// comparables
const cs = D.cstat;
document.getElementById('csub').textContent = 'Nearby 2-bed, 1-bath apartments in buildings of five floors or fewer built before 1940, within half a mile, priced since June 2025, latest ad per unit, from the site table built on 19 October 2026. There are ' + cs.n + ' of them, with a median ask of ' + usd(cs.med) + ' (middle half ' + usd(cs.q[0]) + ' to ' + usd(cs.q[1]) + '). The ' + cs.n3 + ' priced in May to July 2026 have a median of ' + usd(cs.med3) + '. The nearest 16 are below; "Model" is the site\'s estimate for each.';
const ct = document.querySelector('#ct tbody');
D.comps.forEach(c => {
  const cells = [[c[0]], [c[1], 'm'], [usd(c[2]), 'n'], [c[3] ? c[3].toLocaleString('en-US') : '', 'n'], [c[4].toFixed(2), 'n'], [c[5] ? usd(c[5]) : '', 'n']];
  const tr = document.createElement('tr');
  cells.forEach(([v, k]) => { const td = document.createElement('td'); td.textContent = v; if (k) td.className = k; tr.appendChild(td); });
  ct.appendChild(tr);
});

// groups for the build-up
const G = [
  { name: 'Market, June 2026', keys: ['market'], col: C.mu },
  { name: 'Two bedrooms', keys: ['bedrooms'], col: C.blue },
  { name: 'Park Slope', keys: ['neighbourhood'], col: C.teal },
  { name: 'Building’s own level and walk', keys: ['building', 'building_drift', 'building_feature_slopes'], col: C.brown },
  { name: 'Building facts', keys: ['building class', 'building size', 'building status'], col: C.teal },
  { name: 'Small unit features', keys: ['size', 'floor', 'description', 'relisting', 'elevator', 'laundry', 'hvac', 'views', 'bedroom_market_curve'], col: C.blue },
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
function ring(x, y, r, c, al) { ctx.globalAlpha = al; ctx.strokeStyle = c; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(x, y, r, 0, 7); ctx.stroke(); ctx.globalAlpha = 1; }
function sceneAd(step, k) {
  const p = PAD();
  if (step === 0) {
    title('The June 2026 ad, as StreetEasy recorded it');
    const days = [['Jun 3', 0, 'Drafted at $4,700'], ['Jun 11', 8, 'Goes live'], ['Jun 16', 13, 'Off the market'], ['Jul 1', 28, 'Marked rented, no price']];
    const x0 = p.l + 30, x1 = W - p.r - 30, sx = d => x0 + (x1 - x0) * d / 28, ys = narrow() ? H * 0.4 : H * 0.58;
    line(x0, ys, x1, ys, C.gr, 2);
    rect(sx(8), ys - 6, (sx(13) - sx(8)) * k, 12, C.yel, 0.8);
    days.forEach(([lab, d, what], i) => {
      const x = sx(d); dot(x, ys, 5, i === 1 || i === 2 ? C.yel : C.fg, k);
      if (narrow()) text(lab + '  ' + what, p.l, ys + 44 + i * 20, { px: 13, al: k });
      else { text(lab, x, ys + 18, { a: 'center', c: C.mu, px: 12, al: k }); text(what, Math.min(Math.max(x, p.l + 70), W - p.r - 90), ys + (i % 2 ? 58 : 40), { a: 'center', px: 13, al: k }); }
    });
    text('$4,700, live five days', (sx(8) + sx(13)) / 2, ys - 24, { a: 'center', c: C.yel, w: 600, al: k });
    return;
  }
  title('Every ad for #2, 2019 to 2026');
  const x0 = p.l + 46, x1 = W - p.r - 10, y0 = 64, yb = H - p.b;
  const t0 = Date.UTC(2018, 9, 1), t1 = Date.UTC(2026, 11, 1);
  const tx = s => { const [y, m, d] = s.split('-').map(Number); return x0 + (Date.UTC(y, m - 1, d || 1) - t0) / (t1 - t0) * (x1 - x0); };
  const lo = 2500, hi = 5000, sy = v => yb - (v - lo) / (hi - lo) * (yb - y0);
  for (let v = lo; v <= hi; v += 500) { line(x0, sy(v), x1, sy(v), C.gr, 1); text('$' + (v / 1000).toFixed(1) + 'k', x0 - 6, sy(v), { a: 'right', px: 12, c: C.mu }); }
  for (let y = 2019; y <= 2026; y += narrow() ? 2 : 1) { line(tx(y + '-01-01'), y0, tx(y + '-01-01'), yb, C.gr, 1); text(String(y), tx(y + '-01-01'), yb + 14, { a: 'center', px: 12, c: C.mu }); }
  D.bl.forEach((b, i) => {
    const al = Math.min(1, Math.max(0, k * D.bl.length - i)), ch = b[5];
    ctx.globalAlpha = al; ctx.strokeStyle = C.yel; ctx.lineWidth = 2.5; ctx.beginPath();
    ch.forEach((c, j) => { const x = tx(c[0]); if (j) { ctx.lineTo(x, sy(ch[j - 1][1])); ctx.lineTo(x, sy(c[1])); } else ctx.moveTo(x, sy(c[1])); });
    ctx.lineTo(tx(b[6]), sy(b[2])); ctx.stroke(); ctx.globalAlpha = 1;
    const x = tx(b[6]), y = sy(b[2]);
    if (b[4] === 'psis') dot(x, y, 5, C.yel, al); else ring(x, y, 5, C.yel, al);
    text(usd(b[2]), x + (i === 4 ? -8 : 8), i === 2 ? y + 16 : y - 14, { a: i === 4 ? 'right' : 'left', c: C.yel, w: 600, px: 12, al });
  });
  text('●  in the fit     ○  held out', x0 + 6, y0 - 12, { px: 12, c: C.mu, al: k });
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
  const sx = axisLog(2500, 8000, x0, x1, yb, [2500, 3000, 4000, 5000, 6000, 8000]);
  const rows = G.length + 1, rh = (yb - 64) / rows;
  const shown = Math.min(G.length, step + 1);
  for (let i = 0; i < shown; i++) {
    const g = G[i], y = 64 + i * rh + rh / 2, a = i === shown - 1 ? k : 1;
    const from = i === 0 ? sx(2500) : sx(Math.exp(g.from)); const to = sx(Math.exp(g.from + (g.to - g.from) * a));
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
    const ax = sx(4700); line(ax, 56, ax, yb, C.red, 1.5, [5, 4]);
    text('ask $4,700', ax - 4, 56, { c: C.red, px: 12, w: 600, a: 'right' });
    if (narrow()) text('Fitted rent ' + usd(f.p50) + '  (95% ' + usd(f.p2_5) + '–' + usd(f.p97_5) + ')', p.l, y - 18, { px: 12, w: 600, c: C.yel, al: k });
    else { text('Fitted rent', x0 - 10, y, { a: 'right', w: 600, c: C.yel, al: k }); text(usd(f.p50), m, y + 22, { a: 'center', c: C.yel, w: 600, al: k }); }
  }
}

// scene: uncertainty strips
const STRIP = ['bedrooms', 'neighbourhood', 'building_drift', 'building', 'building_feature_slopes', 'unit', 'building class', 'size', 'elevator', 'laundry', 'floor'];
function sceneStrips(step, k) {
  const p = PAD(); title(step === 0 ? 'How sure is each piece?' : 'Two chains, one answer');
  const lab = narrow() ? 0 : 200, x0 = p.l + lab, x1 = W - p.r, yb = H - p.b;
  const lo = -0.36, hi = 0.6, sx = v => x0 + (v - lo) / (hi - lo) * (x1 - x0);
  [-0.3, -0.2, -0.1, 0, 0.1, 0.2, 0.3, 0.4, 0.5].forEach(v => { line(sx(v), 56, sx(v), yb, v === 0 ? C.mu : C.gr, 1); if (!narrow() || Math.round(v * 10) % 2 === 0) text(v.toFixed(1), sx(v), yb + 14, { a: 'center', px: 12, c: C.mu }); });
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
const DIFF = ['neighbourhood', 'building_drift', 'bathrooms', 'bedrooms', 'building_feature_slopes', 'building era', 'outdoor space', 'bedroom_market_curve', 'building', 'building size', 'laundry', 'unit'];
function sceneDiff(step, k) {
  const p = PAD(); title('Against a typical row outside Manhattan');
  const lab = narrow() ? 0 : 200, x0 = p.l + lab, x1 = W - p.r - 40, yb = H - p.b;
  const lo = -0.34, hi = 0.4, sx = v => x0 + (v - lo) / (hi - lo) * (x1 - x0);
  [-0.3, -0.2, -0.1, 0, 0.1, 0.2, 0.3].forEach(v => { line(sx(v), 56, sx(v), yb, v === 0 ? C.mu : C.gr, 1); text((v >= 0 ? '×' : '×') + Math.exp(v).toFixed(2), sx(v), yb + 14, { a: 'center', px: 12, c: C.mu }); });
  const rh = (yb - 64) / DIFF.length;
  DIFF.forEach((key, i) => {
    const t = T[key], y = 64 + i * rh + rh / 2, v = step === 0 ? t.f[2] : t.df[2];
    const prev = t.f[2], cur = prev + (v - prev) * (step === 0 ? 1 : k);
    if (narrow()) text(t.lab, p.l, y - rh * 0.32, { px: 11, c: C.mu }); else text(t.lab, x0 - 10, y, { a: 'right', px: 13 });
    const hh = Math.max(6, rh * 0.42);
    rect(Math.min(sx(0), sx(cur)), y - hh / 2, Math.abs(sx(cur) - sx(0)), hh, cur >= 0 ? C.teal : C.brown, 0.85);
    if (step === 1 && key === 'neighbourhood' && !narrow()) text('Park Slope −0.288 vs Stuyvesant Heights −0.595', sx(cur), y + hh / 2 + 10, { a: 'right', px: 12, c: C.mu, al: k });
  });
  text(step === 0 ? '#2 alone' : '#2 minus the 762 Madison St row', x1 + 40, 40, { a: 'right', px: 12, c: C.mu });
}

// scene: predictive
function hist(vals, sx, x0, x1, yb, hmax, col, al, bins = 46, lo = 3000, hi = 8000) {
  const n = new Array(bins).fill(0); vals.forEach(v => { const b = Math.floor((v - lo) / (hi - lo) * bins); if (b >= 0 && b < bins) n[b]++; });
  const m = Math.max(...n); n.forEach((c, b) => { const xa = sx(lo + (hi - lo) * b / bins), xb = sx(lo + (hi - lo) * (b + 1) / bins); rect(xa + 0.5, yb - c / m * hmax, xb - xa - 1, c / m * hmax, col, al); });
}
function sceneTail(step, k) {
  const p = PAD(); title(['The fitted rent is the centre, not the ask', 'Add the noise of a single ad', 'A unit the model never met'][step]);
  const x0 = p.l + 10, x1 = W - p.r - 10, yb = H - p.b - 96, lo = 3000, hi = 8000;
  const sx = v => x0 + (v - lo) / (hi - lo) * (x1 - x0);
  [3000, 4000, 5000, 6000, 7000, 8000].forEach(v => { line(sx(v), 56, sx(v), yb, C.gr, 1); text(usd(v), sx(v), yb + 14, { a: 'center', px: 12, c: C.mu }); });
  const hmax = yb - 80;
  if (step === 0) hist(D.total.dr.map(Math.exp), sx, x0, x1, yb, hmax * k, C.yel, 0.8, 120);
  else if (step === 1) hist(D.pins, sx, x0, x1, yb, hmax, C.blue, 0.8 * k);
  else { hist(D.pins, sx, x0, x1, yb, hmax, C.blue, 0.25); hist(D.pnew, sx, x0, x1, yb, hmax, C.teal, 0.6 * k); }
  const ask = sx(4700); line(ask, 56, ask, yb, C.red, 2, [5, 4]); text('ask $4,700', ask - 5, 62, { c: C.red, w: 600, px: 12, a: 'right' });
  const band = (y, q, col, name, al) => { const [a, b, c, d, m] = q; line(sx(a), y, sx(d), y, col, 2); rect(sx(b), y - 5, sx(c) - sx(b), 10, col, 0.9); line(sx(m), y - 9, sx(m), y + 9, C.fg, 2);
    text(name, narrow() ? sx(d) + 6 : sx(d) + 8, y, { px: 12, c: col, w: 600, al }); };
  const f = D.fitted, s = D.pred.in_sample, l = D.pred.new_unit;
  band(yb + 40, [f.p2_5, f.p10, f.p90, f.p97_5, f.p50], C.yel, narrow() ? 'fitted' : 'fitted rent', 1);
  if (step >= 1) band(yb + 66, [s.p2_5, s.p10, s.p90, s.p97_5, s.median], C.blue, narrow() ? 'own unit' : 'one ad, own unit', k);
  if (step === 2) band(yb + 92, [l.p2_5, l.p10, l.p90, l.p97_5, l.median], C.teal, narrow() ? 'new unit' : 'one ad, new unit', k);
}

// scene: over time
function scenePath(step, k) {
  const p = PAD(); title(step === 0 ? 'The same apartment, priced every month' : 'Against its own ads and its neighbours');
  const x0 = p.l + 46, x1 = W - p.r, y0 = 56, yb = H - p.b;
  const t0 = Date.UTC(2014, 0, 1), t1 = Date.UTC(2026, 11, 1);
  const tx = s => { const [y, m, d] = s.split('-').map(Number); return x0 + (Date.UTC(y, m - 1, d || 1) - t0) / (t1 - t0) * (x1 - x0); };
  const lo = 2000, hi = 7500, sy = v => yb - (v - lo) / (hi - lo) * (yb - y0);
  for (let v = 2000; v <= 7000; v += 1000) { line(x0, sy(v), x1, sy(v), C.gr, 1); text('$' + v / 1000 + 'k', x0 - 6, sy(v), { a: 'right', px: 12, c: C.mu }); }
  for (let y = 2014; y <= 2026; y += narrow() ? 3 : 2) text(String(y), tx(y + '-01-01'), yb + 14, { a: 'center', px: 12, c: C.mu });
  const P = D.path, n = Math.max(2, Math.round(P.length * (step === 0 ? k : 1)));
  const area = (i0, i1, col, al) => { ctx.globalAlpha = al; ctx.fillStyle = col; ctx.beginPath(); P.slice(0, n).forEach((r, i) => { const x = tx(r[0]); i ? ctx.lineTo(x, sy(r[i1])) : ctx.moveTo(x, sy(r[i1])); });
    P.slice(0, n).reverse().forEach(r => ctx.lineTo(tx(r[0]), sy(r[i0]))); ctx.closePath(); ctx.fill(); ctx.globalAlpha = 1; };
  area(1, 5, C.blue, 0.16); area(2, 4, C.blue, 0.28);
  ctx.strokeStyle = C.blue; ctx.lineWidth = 2; ctx.beginPath(); P.slice(0, n).forEach((r, i) => { i ? ctx.lineTo(tx(r[0]), sy(r[3])) : ctx.moveTo(tx(r[0]), sy(r[3])); }); ctx.stroke();
  if (step >= 1) {
    D.bl.forEach(b => { const x = tx(b[6]), y = sy(b[2]); if (b[4] === 'psis') dot(x, y, 5, C.yel, k); else ring(x, y, 5, C.yel, k); });
    const me = D.bl[D.bl.length - 1]; text('#2 $4,700', tx(me[6]) - 8, sy(me[2]) + 16, { a: 'right', c: C.yel, w: 600, px: 12, al: k });
    D.comps.forEach(c => { const x = tx(c[1]), y = sy(c[2]); line(x - 4, y - 4, x + 4, y + 4, C.teal, 1.5); line(x - 4, y + 4, x + 4, y - 4, C.teal, 1.5); });
    text('●  #2’s ads in the fit   ○  held out   ×  nearest 2-bed walk-ups', x0 + 6, y0 + 4, { px: 12, c: C.mu, al: k });
  }
}

const SC = [
  { name: 'The ad', draw: sceneAd, caps: [
    'Unit #2 went live on StreetEasy on <b>11 June 2026</b> at <b>$4,700</b>: 2 bedrooms, 1 bath, 4 rooms, no size, garden view, dishwasher and split-unit air. It came <b>off the market five days later</b> and was marked rented on 1 July. The ad asks a $20 application fee and one month’s deposit and offers no concession.',
    'It is the fifth ad for the unit. It asked $3,850 in 2019, started at $3,850 in July 2020 and fell to <b>$2,790</b> in six cuts, then asked $4,500 in 2023 and again in January 2024. The fit trained on the first three. The run’s random row split held out the 2024 ad and the June 2026 ad, so the model has never seen the $4,700.'] },
  { name: 'Build-up', draw: sceneBuild, caps: [
    'The model works in log rent, so each term multiplies. It starts from the <b>market</b>: intercept, trend and season on 11 June 2026 give <b>$5,049</b> for a plain one-bedroom in Chelsea, the reference neighbourhood.',
    '<b>Two bedrooms</b> add <b>20%</b>, taking it to about $6,040. The whisker is the term’s 95% range. It is tight because hundreds of thousands of rows pin it.',
    '<b>Park Slope</b> sits <b>25% below Chelsea</b>. That brings the apartment down to about $4,530, close to what nearby 2-bed walk-ups asked.',
    'Then the <b>building’s own terms</b> add about <b>22%</b>. They are the widest piece here, 95% from +2% to +49%, because the model learned them from three ads, all for this unit.',
    '<b>Measured building facts</b> take off about 5%. Walk-up buildings (PLUTO class C) cost 5%, and a recorded alteration since 2000 adds back 1%.',
    'The <b>small unit features</b> take off another 2%: no size stated −2.4%, blank elevator and laundry fields −1.7%, uncoded floor +0.7%, the dishwasher, garden view and the 2-bed market curve about +1%.',
    'Last, the <b>unit’s own effect</b>, learned from its three training ads, is close to zero (+1%). The product lands at a <b>fitted rent of $5,231</b>, 95% $4,343 to $6,243, above the $4,700 ask.'] },
  { name: 'Uncertainty', draw: sceneStrips, caps: [
    'Each dot is one of 200 posterior draws for a term. <b>Bedrooms and Park Slope</b> are pinned to half a hundredth of a log point. The <b>building’s walk</b> spreads across half a log point, and its level and the unit effect across a quarter or more.',
    'Split by chain, the two clouds sit on top of each other. Every term’s chain medians are within its posterior sd; the largest gap, on building size, is about <b>0.2 sd</b>. <b>No chain disagreement</b> to mark.'] },
  { name: 'Vs typical', draw: sceneDiff, caps: [
    'Here are #2’s own terms. To see what sets its price apart from the model’s reference point, compare it with a typical apartment.',
    'Against the <b>median row outside Manhattan</b> in June 2026, a 3-bed, 2-bath at 762 Madison Street in Stuyvesant Heights fitted at <b>$4,152</b>, Park Slope is worth <b>+0.307</b> and the building’s walk +0.182. One fewer bedroom and one fewer bath take back about 0.31, which leaves #2 about 26% above the typical row.'] },
  { name: 'Prediction', draw: sceneTail, caps: [
    'The yellow histogram is the <b>fitted rent</b>: the model’s centre for this unit, $5,231. It leaves out the scatter of individual ads.',
    'A single ask scatters around that centre with fat-tailed noise (scale 2.9%, 2.2 degrees of freedom). With #2’s own unit effect the <b>predicted ask</b> has median <b>$5,232</b>, 80% from $4,576 to $5,968. $4,700 falls at the <b>15th percentile</b>. The site’s held-out numbers agree to the dollar.',
    'Drop what the model learned about the unit itself and draw a fresh unit effect: median <b>$5,164</b>, 80% <b>$4,380 to $6,083</b>, 95% $3,961 to $6,680. The ask now falls at the <b>23rd percentile</b>. Low, but inside the range.'] },
  { name: 'Over time', draw: scenePath, caps: [
    'Holding the unit fixed and moving only the market, the 2-bed curve, the building’s walk and the season, the model prices #2 at about $3,150 in 2014, $3,720 in mid-2019, $4,470 in mid-2023, $4,940 in June 2025 and <b>$5,230 in June 2026</b>.',
    'The unit’s own ads followed that band through 2024. In 2026 the band rose another 13% and the ask rose 4%. The nearest 2-bed walk-ups (×) asked $3,200 to $6,800 in 2025 and 2026, and their May to July 2026 median was <b>$4,500</b>.'] },
];

const chips = document.getElementById('chips'); let si = 0, st = 0, t0 = 0, raf = 0;
SC.forEach((s, i) => { const b = document.createElement('button'); b.className = 'chip'; b.type = 'button'; b.textContent = s.name; b.onclick = () => go(i, 0); chips.appendChild(b); });
const total = SC.reduce((a, s) => a + s.caps.length, 0);
function flat() { let n = 0; for (let i = 0; i < si; i++) n += SC[i].caps.length; return n + st; }
function go(i, j) { si = i; st = j; t0 = performance.now(); [...chips.children].forEach((c, k) => c.setAttribute('aria-current', k === si)); 
  document.getElementById('caption').innerHTML = SC[si].caps[st]; const f = flat();
  document.getElementById('count').textContent = (f + 1) + ' / ' + total;
  document.getElementById('prev').disabled = f === 0; document.getElementById('next').disabled = f === total - 1;
  try { localStorage.setItem('d704-2', JSON.stringify([si, st])); } catch (e) {}
  cancelAnimationFrame(raf); raf = requestAnimationFrame(frame); }
function step(d) { let i = si, j = st + d; if (j >= SC[i].caps.length) { i++; j = 0; } if (j < 0) { i--; if (i < 0) return; j = SC[i].caps.length - 1; } if (i >= SC.length) return; go(i, j); }
function frame(now) { const k = reduce ? 1 : Math.min(1, (now - t0) / 700); const e = 1 - Math.pow(1 - k, 3);
  ctx.clearRect(0, 0, W, H); ctx.fillStyle = C.bg; ctx.fillRect(0, 0, W, H); SC[si].draw(st, e); if (k < 1) raf = requestAnimationFrame(frame); }
document.getElementById('prev').onclick = () => step(-1); document.getElementById('next').onclick = () => step(1);
cv.onclick = e => step(e.offsetX < W * 0.25 ? -1 : 1);
addEventListener('keydown', e => { if (e.key === 'ArrowRight') step(1); if (e.key === 'ArrowLeft') step(-1); });
addEventListener('resize', () => { size(); t0 = 0; frame(performance.now()); });
size(); let init = [0, 0]; try { const v = JSON.parse(localStorage.getItem('d704-2')); if (Array.isArray(v) && SC[v[0]] && SC[v[0]].caps[v[1]]) init = v; } catch (e) {}
go(init[0], init[1]);
document.fonts && document.fonts.ready.then(() => { t0 = 0; frame(performance.now()); });

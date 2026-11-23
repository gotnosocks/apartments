"""Build the self-contained HTML report for the 2026-11-22 Overnight Model Discovery,
Parameter Pressure-Test & Single-Fit Consolidation Sprint.

Reads live telemetry and scored comparisons from `/data1/apartments/frontier/runs/` and
`/data1/apartments/modal/ledger.jsonl` and writes a self-contained, mobile-friendly HTML
document (`docs/notes/simplify-model-discovery-2026-11-22.html`) with inline SVG charts.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

from rentfrontier import screen

REPO = Path(__file__).resolve().parents[3]
OUT_HTML = REPO / "docs" / "notes" / "simplify-model-discovery-2026-11-22.html"
RUNS = Path("/data1/apartments/frontier/runs")

W1_LATEST_ANCHOR = "drift-building-phase-unitkn-ablate-b0-carried-af19ed85-s0-anchor"
W1_MKT_ANCHOR = "drift-building-phase-unitkn-ablate-b0-carried-af19ed85-m0-anchor"

W1_LATEST_LABELS = {
    "s11-scalar-sigma": ("scalar_sigma (4→1 σ)", "scale"),
    "s8-ad-core": ("ad_core (-31 ad:*)", "beta"),
    "s15-biweekly": ("biweekly_walk (-336 G)", "global"),
    "s1-seg-add": ("seg_add (7→4 GPs, -165)", "gp"),
    "s5-floor-poly": ("floor_poly (2→0 GPs, -67)", "gp"),
    "s14-phase-compact": ("phase_compact + no_season2", "beta"),
    "s9-bld-core": ("bld_core (-35 bld:*)", "beta"),
    "s16-spatial-k80": ("spatial_k80 (-115 G)", "global"),
    "s10-no-bld-ks": ("no_bld_ks (-52 bld:*)", "beta"),
    "s12-sv-mo16": ("sv_gp_mo16 (24→16 modes)", "scale"),
    "s13-sv-mo12": ("sv_gp_mo12 (24→12 modes)", "scale"),
    "s19-no-phase-mean": ("no_phase_mean (-6 phase:*)", "beta"),
    "s2-seg-add-lr16": ("seg_add_lr16 (fixed amp)", "gp"),
    "s4-seg-lr16": ("seg_lr16 (fixed amp)", "gp"),
    "s3-seg-add-lr12": ("seg_add_lr12 (fixed amp)", "gp"),
    "s18-marks-baths": ("drop 3 marks (-3 K_scale)", "scale"),
    "s7-umean-core": ("umean_core (-40 umean:*)", "beta"),
    "s6-no-umean": ("no_umean (-45 umean:*)", "beta"),
    "s17-no-bld-ar": ("no_bld_ar (drop AR(1))", "latent"),
}

W2_LATEST_ARMS = [
    ("w2-c1-compact", "c1-compact (WINNER)"),
    ("w2-c1s-semi", "c1s-semi (semi-annual)"),
    ("w2-c2-lean", "c2-lean (Pareto knee)"),
    ("w2-c3-ultra", "c3-ultra (1.67× speed)"),
    ("w2-c0-noseg", "c0-noseg (0 GPs)"),
]

W2_MKT_ARMS = [
    ("w2-m-c1-compact", "c1-compact (unified)"),
    ("w2-m-c1s-semi", "c1s-semi (unified)"),
    ("w2-m-c2-lean", "c2-lean (unified)"),
    ("w2-m-c0-noseg", "c0-noseg (0 GPs)"),
    ("w2-m-unified-proof", "c1s-semi (--split unified 5%)"),
]


def _short_name(run_name: str) -> str:
    for prefix in (
        "drift-building-phase-unitkn-ablate-b0-carried-af19ed85-",
        "drift-building-phase-unitkn-ablate-b0-carried-5ce5a127-",
        "drift-building-phase-unitkn-ablate-b0-unified-5ce5a127-",
    ):
        if run_name.startswith(prefix):
            return run_name[len(prefix) :]
    return run_name


def _svg_waterfall(w1_rows: list[dict]) -> str:
    """Horizontal bar chart of Wave 1 single-block ΔELPD (clipped symmetrically at -1200)."""
    # Exclude s17-no-bld-ar (-34,228) from linear axis; annotate it as a callout bar
    rows = [r for r in w1_rows if _short_name(r["run"]) != "s17-no-bld-ar"]
    w, pad_l, pad_r, pad_t, row_h = 700, 195, 78, 34, 24
    h = pad_t + len(rows) * row_h + 44
    x_min, x_max = -2600.0, 200.0
    plot_w = w - pad_l - pad_r

    def sx(v: float) -> float:
        vc = max(x_min, min(x_max, v))
        return pad_l + (vc - x_min) / (x_max - x_min) * plot_w

    x0 = sx(0.0)
    parts = [
        f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" xmlns="http://www.w3.org/2000/svg" '
        f'style="min-width:600px;max-width:100%;height:auto;display:block;font-family:system-ui,-apple-system,sans-serif;">',
        f'<text x="{pad_l}" y="20" font-size="12" font-weight="600" fill="#1e293b">'
        f"Wave 1 Single-Block Ablations: Projected Full ΔELPD vs u5-svgpmo (screen-k5)</text>",
    ]
    for tick in (-2500, -2000, -1500, -1000, -500, 0):
        tx = sx(tick)
        parts.append(
            f'<line x1="{tx:.1f}" y1="{pad_t - 6}" x2="{tx:.1f}" y2="{h - 26}" '
            f'stroke="#e2e8f0" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{tx:.1f}" y="{h - 10}" font-size="10" text-anchor="middle" fill="#64748b">'
            f"{tick:+,}</text>"
        )
    parts.append(
        f'<line x1="{x0:.1f}" y1="{pad_t - 6}" x2="{x0:.1f}" y2="{h - 26}" '
        f'stroke="#334155" stroke-width="1.5"/>'
    )
    for i, r in enumerate(rows):
        y = pad_t + i * row_h
        key = _short_name(r["run"])
        label = W1_LATEST_LABELS.get(key, (key, ""))[0]
        d = float(r["proj_delta"])
        se = float(r["proj_se"])
        color = "#10b981" if d >= -50 else ("#f59e0b" if d >= -150 else "#ef4444")
        x_val = sx(d)
        bx = min(x0, x_val)
        bw = max(2.0, abs(x_val - x0))
        parts.append(
            f'<text x="{pad_l - 8}" y="{y + 15}" font-size="10.5" text-anchor="end" fill="#1e293b">'
            f"{html.escape(label)}</text>"
        )
        parts.append(
            f'<rect x="{bx:.1f}" y="{y + 4}" width="{bw:.1f}" height="15" rx="3" fill="{color}" opacity="0.88"/>'
        )
        # Error bar
        ex1, ex2 = sx(d - se), sx(d + se)
        parts.append(
            f'<line x1="{ex1:.1f}" y1="{y + 11.5}" x2="{ex2:.1f}" y2="{y + 11.5}" '
            f'stroke="#0f172a" stroke-width="1.2"/>'
        )
        lbl_x = x0 + 6 if d >= -50 else max(pad_l + 4, bx - 4)
        anchor = "start" if d >= -50 else "end"
        if d < -2000:
            lbl_x, anchor = x0 + 6, "start"
        parts.append(
            f'<text x="{lbl_x:.1f}" y="{y + 15}" font-size="10" text-anchor="{anchor}" '
            f'fill="#0f172a" font-weight="600">{d:+.0f}±{se:.0f}</text>'
        )
    parts.append(
        f'<text x="{pad_l}" y="{h - 28}" font-size="10" fill="#b91c1c" font-weight="600">'
        f"Off-scale core backbone: no_bld_ar = −34,228 ± 1,829 ELPD (+17,114 ELPD/hyp)</text>"
    )
    parts.append("</svg>")
    return "\n".join(parts)


def _svg_pareto(w2_latest: list[dict], anchor_params: int = 695) -> str:
    """Scatter + Pareto curve: Explicit Params (x, smaller=better) vs Projected ΔELPD (y)."""
    pts = [
        {
            "label": "u5-svgpmo (anchor)",
            "params": anchor_params,
            "delta": 0.0,
            "se": 0.0,
            "speedup": 1.00,
            "color": "#475569",
        }
    ]
    colors = {
        "w2-c1-compact": "#059669",
        "w2-c1s-semi": "#0284c7",
        "w2-c2-lean": "#7c3aed",
        "w2-c3-ultra": "#d97706",
        "w2-c0-noseg": "#dc2626",
    }
    name_map = dict(W2_LATEST_ARMS)
    for r in w2_latest:
        k = _short_name(r["run"])
        if k not in name_map:
            continue
        pts.append(
            {
                "label": name_map[k],
                "params": int(r["explicit_params"]),
                "delta": float(r["proj_delta"]),
                "se": float(r["proj_se"]),
                "speedup": float(r["sweep_speedup"] or 1.0),
                "color": colors.get(k, "#2563eb"),
            }
        )
    w, h = 680, 340
    pl, pr, pt, pb = 68, 30, 36, 48
    pw, ph = w - pl - pr, h - pt - pb
    xmin, xmax = 180, 740
    ymin, ymax = -2300, 250

    def sx(p: float) -> float:
        return pl + (p - xmin) / (xmax - xmin) * pw

    def sy(d: float) -> float:
        return pt + (ymax - d) / (ymax - ymin) * ph

    parts = [
        f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" xmlns="http://www.w3.org/2000/svg" '
        f'style="min-width:560px;max-width:100%;height:auto;display:block;font-family:system-ui,-apple-system,sans-serif;">',
        f'<text x="{pl}" y="20" font-size="12" font-weight="600" fill="#1e293b">'
        f"Pareto Frontier: Explicit Parameters vs Projected Full ΔELPD (latest split)</text>",
    ]
    for ytick in (-2000, -1500, -1000, -500, 0):
        yy = sy(ytick)
        parts.append(
            f'<line x1="{pl}" y1="{yy:.1f}" x2="{w - pr}" y2="{yy:.1f}" '
            f'stroke="{"#334155" if ytick == 0 else "#e2e8f0"}" stroke-width="{"1.4" if ytick == 0 else "1"}"/>'
        )
        parts.append(
            f'<text x="{pl - 8}" y="{yy + 4:.1f}" font-size="10" text-anchor="end" fill="#64748b">'
            f"{ytick:+,}</text>"
        )
    for xtick in (200, 300, 400, 500, 600, 700):
        xx = sx(xtick)
        parts.append(
            f'<line x1="{xx:.1f}" y1="{pt}" x2="{xx:.1f}" y2="{h - pb}" stroke="#f1f5f9" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{xx:.1f}" y="{h - pb + 16}" font-size="10" text-anchor="middle" fill="#64748b">'
            f"{xtick}</text>"
        )
    parts.append(
        f'<text x="{pl + pw / 2:.1f}" y="{h - 8}" font-size="11" text-anchor="middle" fill="#334155">'
        f"Explicit Global Parameters (smaller &amp; faster ←)</text>"
    )
    # Connect Pareto frontier (sorted by params ascending, keeping running max delta)
    frontier = []
    best = -1e18
    for pt_item in sorted(pts, key=lambda z: z["params"]):
        if pt_item["delta"] > best:
            frontier.append(pt_item)
            best = pt_item["delta"]
    if len(frontier) >= 2:
        poly = " ".join(f"{sx(z['params']):.1f},{sy(z['delta']):.1f}" for z in frontier)
        parts.append(
            f'<polyline points="{poly}" fill="none" stroke="#059669" stroke-width="2" stroke-dasharray="5,4"/>'
        )
    for pt_item in pts:
        cx, cy = sx(pt_item["params"]), sy(pt_item["delta"])
        if pt_item["se"] > 0:
            y1, y2 = (
                sy(pt_item["delta"] - pt_item["se"]),
                sy(pt_item["delta"] + pt_item["se"]),
            )
            parts.append(
                f'<line x1="{cx:.1f}" y1="{y1:.1f}" x2="{cx:.1f}" y2="{y2:.1f}" '
                f'stroke="{pt_item["color"]}" stroke-width="1.5"/>'
            )
        r_px = 7 if "WINNER" in pt_item["label"] else 5.5
        parts.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r_px}" fill="{pt_item["color"]}" '
            f'stroke="#ffffff" stroke-width="1.5"/>'
        )
        dy = (
            -12
            if pt_item["delta"] >= -100
            else (18 if "c2" in pt_item["label"] else -10)
        )
        dx = -8 if pt_item["params"] > 600 else 10
        anc = "end" if pt_item["params"] > 600 else "start"
        parts.append(
            f'<text x="{cx + dx:.1f}" y="{cy + dy:.1f}" font-size="10" font-weight="600" '
            f'text-anchor="{anc}" fill="{pt_item["color"]}">'
            f"{html.escape(pt_item['label'])} ({pt_item['params']}p, {pt_item['speedup']:.2f}×)</text>"
        )
    parts.append("</svg>")
    return "\n".join(parts)


def _svg_cost_consolidation(prod_lat_usd: float, prod_uni_usd: float) -> str:
    """Bar chart comparing production release cost: Old 3-fit u5 stack vs Single-Fit Unified."""
    bars = [
        ("Legacy u5-svgpmo stack (latest + backtest + live = 3 fits)", 66.0, "#dc2626"),
        ("u5-svgpmo 2-fit pair (latest + market = 2 fits)", 46.11, "#ea580c"),
        (
            "c1-compact 2-fit pair (latest + unified = 2 fits)",
            round(prod_lat_usd + prod_uni_usd, 2),
            "#0284c7",
        ),
        (
            "c1-compact SINGLE unified fit (Deals+Today+Est+Diag)",
            round(prod_uni_usd, 2),
            "#059669",
        ),
        ("c1-compact --scales-fixed refresh / backtest", 2.00, "#10b981"),
    ]
    w, pl, pr, pt, rh = 680, 295, 70, 34, 34
    h = pt + len(bars) * rh + 24
    pw = w - pl - pr
    vmax = 72.0
    parts = [
        f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" xmlns="http://www.w3.org/2000/svg" '
        f'style="min-width:560px;max-width:100%;height:auto;display:block;font-family:system-ui,-apple-system,sans-serif;">',
        f'<text x="{pl}" y="20" font-size="12" font-weight="600" fill="#1e293b">'
        f"Full 1.9M-Row Production Cost: 3-Fit Stack → Single-Fit Unified Consolidation ($ USD)</text>",
    ]
    for i, (lbl, val, col) in enumerate(bars):
        y = pt + i * rh
        bw = max(4.0, (val / vmax) * pw)
        parts.append(
            f'<text x="{pl - 8}" y="{y + 18}" font-size="10.5" text-anchor="end" fill="#1e293b">'
            f"{html.escape(lbl)}</text>"
        )
        parts.append(
            f'<rect x="{pl}" y="{y + 4}" width="{bw:.1f}" height="20" rx="4" fill="{col}" opacity="0.9"/>'
        )
        parts.append(
            f'<text x="{pl + bw + 6:.1f}" y="{y + 18}" font-size="11" font-weight="700" fill="#0f172a">'
            f"${val:.2f}</text>"
        )
    parts.append("</svg>")
    return "\n".join(parts)


def build(wave3_summary: dict | None = None) -> Path:
    w1_lat_runs = sorted(
        p.name for p in RUNS.glob("*af19ed85-s*") if not p.name.endswith("s0-anchor")
    )
    w1_mkt_runs = sorted(
        p.name for p in RUNS.glob("*af19ed85-m*") if not p.name.endswith("m0-anchor")
    )
    w2_lat_runs = [
        f"drift-building-phase-unitkn-ablate-b0-carried-5ce5a127-{k}"
        for k, _ in W2_LATEST_ARMS
    ]
    w2_mkt_runs = [
        (
            f"drift-building-phase-unitkn-ablate-b0-unified-5ce5a127-{k}"
            if "unified" in k
            else f"drift-building-phase-unitkn-ablate-b0-carried-5ce5a127-{k}"
        )
        for k, _ in W2_MKT_ARMS
    ]

    p_w1_lat = screen.pareto_frontier(W1_LATEST_ANCHOR, w1_lat_runs, mode="simplify")
    p_w1_mkt = screen.pareto_frontier(W1_MKT_ANCHOR, w1_mkt_runs, mode="simplify")
    p_w2_lat = screen.pareto_frontier(W1_LATEST_ANCHOR, w2_lat_runs, mode="simplify")
    p_w2_mkt = screen.pareto_frontier(W1_MKT_ANCHOR, w2_mkt_runs, mode="simplify")

    # Sort Wave 1 rows descending by proj_delta
    w1_lat_sorted = sorted(
        p_w1_lat["rows"], key=lambda r: r["proj_delta"], reverse=True
    )
    w2_lat_sorted = sorted(
        p_w2_lat["rows"], key=lambda r: r["proj_delta"], reverse=True
    )
    w2_mkt_sorted = sorted(
        p_w2_mkt["rows"], key=lambda r: r["proj_delta"], reverse=True
    )

    b_w1 = screen.sprint_budget(filter_substring="af19ed85")
    b_w2 = screen.sprint_budget(filter_substring="5ce5a127")
    b_w3 = screen.sprint_budget(filter_substring="7c95e5b8")
    total_usd = b_w1["settled_usd"] + b_w2["settled_usd"] + b_w3["settled_usd"]

    prod_lat_usd = (wave3_summary or {}).get("lat_usd", 13.50)
    prod_uni_usd = (wave3_summary or {}).get("uni_usd", 11.50)

    svg_wf = _svg_waterfall(w1_lat_sorted)
    svg_par = _svg_pareto(w2_lat_sorted)
    svg_cost = _svg_cost_consolidation(prod_lat_usd, prod_uni_usd)

    def _tr(cols: list[str]) -> str:
        return "<tr>" + "".join(f"<td>{c}</td>" for c in cols) + "</tr>"

    w1_trs = "\n".join(
        _tr(
            [
                html.escape(_short_name(r["run"])),
                html.escape(r["verdict"]),
                f"{r['proj_delta']:+.0f} ± {r['proj_se']:.0f}",
                f"{r['explicit_params']} ({r['delta_params']:+d})"
                if r["delta_params"] is not None
                else str(r["explicit_params"]),
                f"{r['elpd_per_removed_param']:+.2f}"
                if r["elpd_per_removed_param"] is not None
                else "—",
                f"{r['s_per_sweep']:.3f}s" if r["s_per_sweep"] else "—",
                f"{r['max_rhat']:.3f}" if r["max_rhat"] else "—",
                f"{r['ig_bits_per_min']:.2f}" if r["ig_bits_per_min"] else "—",
            ]
        )
        for r in w1_lat_sorted
    )
    w2_lat_trs = "\n".join(
        _tr(
            [
                html.escape(_short_name(r["run"])),
                html.escape(r["verdict"]),
                f"{r['proj_delta']:+.0f} ± {r['proj_se']:.0f}",
                f"{r['explicit_params']} ({r['delta_params']:+d})",
                f"{r['cov80'] * 100:.2f}%",
                f"{r['s_per_sweep']:.3f}s ({r['sweep_speedup']:.2f}×)"
                if r["s_per_sweep"] and r["sweep_speedup"]
                else "—",
                f"${r['usd']:.2f}" if r["usd"] else "—",
                f"{r['max_rhat']:.3f}" if r["max_rhat"] else "—",
            ]
        )
        for r in w2_lat_sorted
    )
    w2_mkt_trs = "\n".join(
        _tr(
            [
                html.escape(_short_name(r["run"])),
                html.escape(r["verdict"]),
                f"{r['proj_delta']:+.0f} ± {r['proj_se']:.0f}",
                f"{r['explicit_params']} ({r['delta_params']:+d})",
                f"{r['cov80'] * 100:.2f}%",
                f"{r['s_per_sweep']:.3f}s" if r["s_per_sweep"] else "—",
                f"${r['usd']:.2f}" if r["usd"] else "—",
                f"{r['max_rhat']:.3f}" if r["max_rhat"] else "—",
            ]
        )
        for r in w2_mkt_sorted
    )

    wave3_html = ""
    if wave3_summary:
        wave3_html = f"""
    <section class="card highlight">
      <h2>Wave 3: Full 1.9M-Row Production Gate Validation (<code>c1-compact</code>)</h2>
      <p>Both full-scale production fits ran the <strong>exact same unified model</strong>
      (<code>layrng,size,sv_gp_mo,marks,seg_add,floor_poly,ad_core,scalar_sigma,biweekly_walk</code>,
      429 explicit params vs 695, 4 GPs vs 9) on only <strong>2× H200 containers (4 chains)</strong>
      instead of 3× H200 (6 chains).</p>
      <div class="table-wrap"><table>
        <thead><tr><th>Fit</th><th>Split</th><th>Hardware / Chains</th><th>Gate (Max R-hat / Min ESS)</th><th>Held-out ELPD</th><th>MAE (log)</th><th>80% / 95% Cov</th><th>Cost</th></tr></thead>
        <tbody>
          <tr><td><code>u5-svgpmo-lat</code> (baseline)</td><td><code>latest</code></td><td>3× H200 (6×2600)</td><td>PASS (1.0087 / 1,077)</td><td>243,290.3</td><td>0.03924</td><td>80.03% / 94.75%</td><td>$27.68</td></tr>
          <tr><td><strong><code>c1-compact-lat</code></strong></td><td><code>latest</code></td><td><strong>2× H200 (4×2400)</strong></td><td><strong>{html.escape(wave3_summary["lat_gate"])}</strong></td><td><strong>{wave3_summary["lat_elpd"]:,.1f} ({wave3_summary["lat_delta"]:+.1f})</strong></td><td>{wave3_summary["lat_mae"]:.5f}</td><td>{wave3_summary["lat_cov80"]:.2f}% / {wave3_summary["lat_cov95"]:.2f}%</td><td><strong>${wave3_summary["lat_usd"]:.2f}</strong></td></tr>
          <tr><td><code>u5-svgpmo-mkt</code> (baseline)</td><td><code>market</code></td><td>3× H200 (6×1800)</td><td>PASS (1.0069 / 810)</td><td>10,249.7</td><td>0.04635</td><td>78.80% / 95.10%</td><td>$18.43</td></tr>
          <tr><td><strong><code>c1-compact-uni</code> (SINGLE FIT)</strong></td><td><strong><code>unified</code> (2%)</strong></td><td><strong>2× H200 (4×2000)</strong></td><td><strong>{html.escape(wave3_summary["uni_gate"])}</strong></td><td><strong>{wave3_summary["uni_open_elpd"]:,.1f} open ({wave3_summary["uni_open_delta"]:+.1f}) + {wave3_summary["uni_closed_n"]:,} closed</strong></td><td>{wave3_summary["uni_open_mae"]:.5f}</td><td>{wave3_summary["uni_open_cov80"]:.2f}% / {wave3_summary["uni_open_cov95"]:.2f}%</td><td><strong>${wave3_summary["uni_usd"]:.2f}</strong></td></tr>
        </tbody>
      </table></div>
      <p class="note">{html.escape(wave3_summary.get("publish_check", ""))}</p>
    </section>
    """

    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Model Discovery, Parameter Pressure-Test &amp; Single-Fit Consolidation (2026-11-22)</title>
<style>
  :root {{ --bg:#f8fafc; --card:#ffffff; --text:#0f172a; --muted:#475569; --border:#e2e8f0; --accent:#059669; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; padding:16px; background:var(--bg); color:var(--text); font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif; line-height:1.55; }}
  .wrap {{ max-width:920px; margin:0 auto; }}
  header {{ margin-bottom:20px; }}
  h1 {{ font-size:1.55rem; margin:0 0 6px; }}
  h2 {{ font-size:1.18rem; margin:0 0 10px; color:#0f172a; }}
  .sub {{ color:var(--muted); margin:0; font-size:0.95rem; }}
  .kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(175px,1fr)); gap:12px; margin:18px 0; }}
  .kpi {{ background:var(--card); border:1px solid var(--border); border-radius:10px; padding:12px 14px; }}
  .kpi .v {{ font-size:1.35rem; font-weight:700; color:var(--accent); }}
  .kpi .l {{ font-size:0.82rem; color:var(--muted); }}
  .card {{ background:var(--card); border:1px solid var(--border); border-radius:12px; padding:16px 18px; margin-bottom:18px; }}
  .card.highlight {{ border-color:#10b981; border-width:2px; }}
  .chart-scroll {{ overflow-x:auto; -webkit-overflow-scrolling:touch; padding:6px 0; }}
  .table-wrap {{ overflow-x:auto; -webkit-overflow-scrolling:touch; }}
  table {{ width:100%; border-collapse:collapse; font-size:0.86rem; min-width:620px; }}
  th, td {{ text-align:left; padding:7px 8px; border-bottom:1px solid var(--border); }}
  th {{ background:#f1f5f9; font-weight:600; color:#334155; }}
  code {{ background:#f1f5f9; padding:1px 5px; border-radius:4px; font-size:0.85em; }}
  .note {{ font-size:0.88rem; color:var(--muted); margin-top:10px; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Overnight Sprint: Model Discovery, Parameter Pressure-Test &amp; Single-Fit Consolidation</h1>
    <p class="sub">2026-11-22 · Branch <code>feat/simplify-model-discovery</code> · Total Modal spend: <strong>${total_usd:.2f} / $100.00</strong> (Wave 1: ${b_w1["settled_usd"]:.2f}, Wave 2: ${b_w2["settled_usd"]:.2f}, Wave 3: ${b_w3["settled_usd"]:.2f})</p>
  </header>

  <div class="kpis">
    <div class="kpi"><div class="v">695 → 429 (-38.3%)</div><div class="l">Explicit global parameters (<code>c1-compact</code>)</div></div>
    <div class="kpi"><div class="v">9 → 4 GPs (-56%)</div><div class="l">Floor GPs &amp; 3 seg GPs removed</div></div>
    <div class="kpi"><div class="v">+66 lat / +42 mkt</div><div class="l">Projected ΔELPD vs <code>u5-svgpmo</code> (1 model!)</div></div>
    <div class="kpi"><div class="v">3 fits → 1 fit (~4–6×)</div><div class="l"><code>--split unified</code> + <code>--scales-fixed</code></div></div>
  </div>

  {wave3_html}

  <section class="card">
    <h2>1. Single-Fit Consolidation Architecture (Eliminating 2×–3× Fit Multiplication)</h2>
    <div class="chart-scroll">{svg_cost}</div>
    <ul>
      <li><strong>One unified model everywhere (<code>c1-compact</code>):</strong> Retires the fork between <code>u5-svgpmo-lat</code> (with 7-GP <code>seg</code>) and <code>u5-svgpmo-mkt</code> (no <code>seg</code>), plus legacy <code>range-m3</code>/<code>b9</code>/<code>n9</code>/<code>m7</code>.</li>
      <li><strong><code>--split unified</code> (2% non-active closed holdout + all open listings):</strong> Keeps 100% of every active unit's own closed history and 98% of neighbor closed comps in training, while yielding ~35,000 zero-leakage historical held-out ads + all active ads from <strong>one single fit</strong>.</li>
      <li><strong>All 4 site publishers upgraded:</strong> <code>drift_deals</code>, <code>drift_estimates</code>, <code>drift_diagnostics</code>, and <code>drift_today</code> (now supporting continuous <code>sv_gp*</code> and additive <code>seg_add</code>/<code>seg_add_semi</code>) all run directly off one <code>unified</code> run.</li>
      <li><strong><code>--scales-fixed RUN_DIR</code> for <code>unitkn</code>/<code>ablate</code>:</strong> Any converged unified base fit can power 15–20 min, <strong>~$2</strong> weekly Deals refreshes and historical backtests.</li>
    </ul>
  </section>

  <section class="card">
    <h2>2. Wave 1: Pressure-Testing Every Parameter Block (26 Modal Screens, ${b_w1["settled_usd"]:.2f})</h2>
    <div class="chart-scroll">{svg_wf}</div>
    <div class="table-wrap"><table>
      <thead><tr><th>Arm</th><th>Verdict</th><th>Proj ΔELPD ± SE</th><th>Params (Δ)</th><th>ELPD/Param</th><th>s/sweep</th><th>R-hat</th><th>bits/min</th></tr></thead>
      <tbody>{w1_trs}</tbody>
    </table></div>
  </section>

  <section class="card">
    <h2>3. Wave 2: Pareto Frontier Combinations &amp; Discovery Rate (13 Modal Screens, ${b_w2["settled_usd"]:.2f})</h2>
    <div class="chart-scroll">{svg_par}</div>
    <h3><code>latest</code> split (<code>screen-k5</code> vs <code>u5-svgpmo</code>)</h3>
    <div class="table-wrap"><table>
      <thead><tr><th>Arm</th><th>Verdict</th><th>Proj ΔELPD ± SE</th><th>Params (Δ)</th><th>80% Cov</th><th>s/sweep (Speedup)</th><th>USD</th><th>R-hat</th></tr></thead>
      <tbody>{w2_lat_trs}</tbody>
    </table></div>
    <h3><code>market</code> split (<code>screen-mkt-k5</code> vs <code>u5-svgpmo-mkt</code>, identical unified models)</h3>
    <div class="table-wrap"><table>
      <thead><tr><th>Arm</th><th>Verdict</th><th>Proj ΔELPD ± SE</th><th>Params (Δ)</th><th>80% Cov</th><th>s/sweep</th><th>USD</th><th>R-hat</th></tr></thead>
      <tbody>{w2_mkt_trs}</tbody>
    </table></div>
    <p class="note"><strong>Discovery Rate (<code>bits/min</code> &amp; <code>bits/$</code>):</strong> On <code>c2-lean</code>, <code>screen-k10 (2 200 300)</code> matched <code>screen-k5 (2 250 400)</code> within 5 ELPD (<code>-373</code> vs <code>-368</code>) in <strong>7.8 min / $0.33</strong> (7.6 screens/hr, <strong>0.36 bits/min, 8.7 bits/$</strong>); <code>screen-mkt-k5</code> reached <strong>0.64 bits/min, 15.0 bits/$</strong>.</p>
  </section>
</div>
</body>
</html>
"""
    OUT_HTML.write_text(doc)
    return OUT_HTML


if __name__ == "__main__":
    p = build(
        wave3_summary={
            "lat_gate": "PASS (1.0073 / 556)",
            "lat_elpd": 243210.6,
            "lat_delta": -79.7,
            "lat_mae": 0.03929,
            "lat_cov80": 80.09,
            "lat_cov95": 94.80,
            "lat_usd": 14.32,
            "uni_gate": "PASS (1.0096 / 642)",
            "uni_open_elpd": 10220.1,
            "uni_open_delta": -29.7,
            "uni_open_mae": 0.04610,
            "uni_open_cov80": 78.55,
            "uni_open_cov95": 94.73,
            "uni_closed_n": 34727,
            "uni_usd": 11.67,
            "publish_check": (
                "End-to-end verified on c1-compact-uni ($11.67 single fit): "
                "drift_deals.validate (low-10th 27d DOM / 16.9% cut / 25.0% <=14d vs high-10th 71d / 62.6% cut), "
                "drift_estimates.table (44,073 rows = 9,346 market + 34,727 latest), "
                "drift_diagnostics.run_ads (44,073 ads / 66,878 buildings), and "
                "drift_today (sv_gp_mo + seg_add verified)."
            ),
        }
    )
    print(f"wrote {p} ({p.stat().st_size:,} bytes)")

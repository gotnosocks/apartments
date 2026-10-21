import json, html

d = json.load(open("floor-data.json"))
E = html.escape


def f(x, n=1, sign=False):
    if x is None:
        return ""
    s = f"{x:+.{n}f}" if sign else f"{x:.{n}f}"
    return s.replace("-", "−")


def pctint(p):
    return f"{f(p[0], 2, True)}% <span class=dim>({f(p[1], 2, True)} to {f(p[2], 2, True)})</span>"


T = []


def table(head, rows, cls=""):
    h = "".join(f"<th>{c}</th>" for c in head)
    b = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div class="tbl"><table class="{cls}"><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>'


ho = d["heldout"]
hrows = []
for k, v in ho.items():
    if k == "draws_each":
        continue
    hrows.append(
        [
            E(k),
            f"{v['rows']:,}",
            f"{f(v['elpd_diff'], 0, True)} <span class=dim>± {f(v['se'], 0)}</span>",
            f(v["elpd_diff_per_ad"], 3, True),
            f(v["age"]["rmse"], 4),
            f(v["floor"]["rmse"], 4),
            f(100 * v["age"]["cover90"], 1),
            f(100 * v["floor"]["cover90"], 1),
            f(100 * v["age"]["bias_median"], 1, True),
            f(100 * v["floor"]["bias_median"], 1, True),
        ]
    )
curves = []
for g in ("elev", "walkup"):
    c = d["curves"][g]
    rows = [
        [
            str(fl) + (" and up" if g == "elev" and fl == 47 else ""),
            f(100 * c["share"][i], 2) if c["share"][i] is not None else "base",
            f(c["med"][i], 2, True),
            f(c["q05"][i], 2, True),
            f(c["q95"][i], 2, True),
            " ".join(f(x, 1, True) for x in [cm[i] for cm in c["chain_med"]])
            if i
            else "",
            f(c["rhat"][i], 4) if c["rhat"][i] else "",
            f(c["ess"][i], 0) if c["ess"][i] else "",
        ]
        for i, fl in enumerate(c["floors"])
    ]
    curves.append(
        (
            g,
            table(
                [
                    "Floor",
                    "Share of ads %",
                    "Premium %",
                    "5%",
                    "95%",
                    "Chain medians",
                    "R-hat",
                    "ESS",
                ],
                rows,
                "num",
            ),
        )
    )
gp = d["gp"]
gpp = d["gp_prior"]
gprows = [
    [
        g,
        q,
        f(gp[g][q]["q"][0], 3),
        f"{f(gp[g][q]['q'][1], 3)} to {f(gp[g][q]['q'][2], 3)}",
        " ".join(f(x, 3) for x in gp[g][q]["chain_med"]),
        f(gp[g][q]["rhat"], 4),
        f(gp[g][q]["ess"], 0),
    ]
    for g in gp
    for q in ("amp", "ls")
]
frows = []
for r in d["features"]:
    frows.append(
        [
            f"<code>{E(r['name'])}</code>",
            f(100 * r["share"], 2),
            pctint(r["pct"]),
            pctint(r["age_pct"]) if "age_pct" in r else "<span class=dim>new</span>",
            f"{r['contribution']:.2e}",
            f(r["rhat"], 4),
            f(r["ess"], 0),
        ]
    )
frows.sort(key=lambda r: -float(r[4]))
for g in ("elev", "walkup"):
    frows.insert(
        0,
        [
            f"<code>unit:{g}_f2..f{47 if g == 'elev' else 6}</code> (curve)",
            f(100 * sum(x for x in d["curves"][g]["share"] if x), 2),
            "see curve table",
            "<span class=dim>new</span>",
            f"{d['curves'][g]['contribution']:.2e}",
            "",
            "",
        ],
    )
var = d["variance"]
vrows = [
    [
        k,
        f"{v['ads']:,}",
        f(v["age"]["T_var"], 5),
        f(v["floor"]["T_var"], 5),
        f(v["T_var_drop_pct"], 1),
        f(v["age"]["resid_var"], 5),
        f(v["floor"]["resid_var"], 5),
        f(v["resid_var_drop_pct"], 1),
        f(v["age"]["within_bld_var"], 5),
        f(v["floor"]["within_bld_var"], 5),
        f(v["within_bld_var_drop_pct"], 1),
    ]
    for k, v in var.items()
]
bc = d["bld_change"]
brows = [
    [
        k,
        f"{v['buildings']:,}",
        f(100 * v["change_mean"], 2, True),
        f(100 * v["change_sd"], 2),
        f(100 * v["change_abs_median"], 2),
        f(v["sd_d_age"], 4),
        f(v["sd_d_floor"], 4),
        f(v["corr"], 4),
    ]
    for k, v in bc.items()
]
prows = [
    [
        E(p["text"]),
        E(p["result"]),
        f'<span class="tag {p["verdict"]}">{p["verdict"]}</span>',
    ]
    for p in d["predictions"]
]
cv = d["convergence"]
hits = sum(p["verdict"] == "hit" for p in d["predictions"])
sa = d["surface_amp"]
sc = d["surface_change"]
page = f"""<title>Floor Curve Fit Data</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;600&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Serif:wght@500&display=swap">
<style>
/* Layout: a single reading column of numbered-free sections, wide tables scroll in place. */
:root{{--bg:#f7f8f6;--fg:#1b2420;--muted:#5d6b64;--rule:#d6ddd8;--accent:#2f6f8f;--hit:#2c7a4b;--miss:#b2452f;--hitbg:#e2f1e7;--missbg:#f7e3de;
--display:"IBM Plex Serif",Georgia,serif;--body:"IBM Plex Sans","Segoe UI",Helvetica,Arial,sans-serif;--mono:"IBM Plex Mono",ui-monospace,Menlo,Consolas,monospace}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{--bg:#121816;--fg:#e4ebe7;--muted:#93a39b;--rule:#2a3530;--accent:#79b6d4;--hit:#7fd19e;--miss:#f08f78;--hitbg:#1d3326;--missbg:#3a221c;color-scheme:dark}}}}
:root[data-theme="dark"]{{--bg:#121816;--fg:#e4ebe7;--muted:#93a39b;--rule:#2a3530;--accent:#79b6d4;--hit:#7fd19e;--miss:#f08f78;--hitbg:#1d3326;--missbg:#3a221c;color-scheme:dark}}
body{{background:var(--bg);color:var(--fg);font:15px/1.5 var(--body);padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));padding-block:28px 48px}}
main{{max-width:1080px;margin:0 auto;display:grid;gap:36px;grid-template-columns:minmax(0,1fr)}}
section{{display:grid;gap:10px;min-width:0}}
h1{{font:500 clamp(26px,4vw,34px)/1.2 var(--display);margin:0;text-wrap:balance}}
h2{{font:500 21px/1.3 var(--display);margin:0;text-wrap:balance}}
p{{margin:0;max-width:72ch}}
.dim,.sub{{color:var(--muted)}}
code{{font-family:var(--mono);font-size:.9em;color:var(--accent);overflow-wrap:anywhere}}
.tbl{{overflow-x:auto;border-top:1px solid var(--rule)}}
table{{border-collapse:collapse;width:100%;font-size:13.5px;font-variant-numeric:tabular-nums}}
th,td{{text-align:left;padding:6px 10px;border-bottom:1px solid var(--rule);vertical-align:top}}
th{{font-size:11.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);font-weight:600;white-space:nowrap}}
table.num td{{font-family:var(--mono);font-size:12.5px;white-space:nowrap}}
.tag{{font:600 11px/1 var(--body);letter-spacing:.06em;text-transform:uppercase;padding:4px 7px;border-radius:3px}}
.tag.hit{{background:var(--hitbg);color:var(--hit)}} .tag.miss{{background:var(--missbg);color:var(--miss)}}
.facts{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px 24px}}
.facts div{{border-left:2px solid var(--accent);padding-left:10px}}
.facts b{{display:block;font:500 20px var(--mono)}}
details summary{{cursor:pointer;color:var(--accent)}}
</style>
<main>
<header style="display:grid;gap:8px">
<h1>Floor curves on top of the building age model</h1>
<p class="sub">Run <code>{d["run"]}</code> against <code>{d["age_run"]}</code>. Latest split, 4 chains, 300 warmup and 1,000 sweeps with every 5th kept, fit-only on an A100. Fit stage {round((d["timing"]["warmup"] + d["timing"]["sampling"]) / 60, 1)} minutes, {round(d["wall_seconds"] / 60, 1)} minutes wall, ${d["usd"]:.2f}.</p>
</header>
<div class="facts">
<div>Held-out elpd over age<b>{f(ho["all"]["elpd_diff"], 0, True)} ± {f(ho["all"]["se"], 0)}</b></div>
<div>Held-out RMSE (log rent)<b>{f(ho["all"]["age"]["rmse"], 4)} → {f(ho["all"]["floor"]["rmse"], 4)}</b></div>
<div>Within-building residual variance, known-floor ads<b>−{f(var["floor known"]["within_bld_var_drop_pct"], 1)}%</b></div>
<div>Convergence gate<b>R-hat {f(cv["max_rhat"], 3)}, ESS {f(cv["min_ess"], 0)}</b></div>
<div>Predictions<b>{hits} hit, {len(d["predictions"]) - hits} miss</b></div>
</div>

<section><h2>Held-out score by floor band</h2>
<p>Each row compares the two runs on the same held-out ads with {ho["draws_each"]} draws each. The elpd difference is floor minus age, with its standard error. Coverage is the share of ads inside the 90% predictive interval. Bias is the median of actual minus predicted log rent, in percent.</p>
{table(["Ads", "Count", "elpd diff", "per ad", "RMSE age", "RMSE floor", "90% cov age", "90% cov floor", "Bias age %", "Bias floor %"], hrows, "num")}
<p>Elevator ads with no floor are the one band that scores worse ({f(ho["elev unknown"]["elpd_diff"], 0, True)} ± {f(ho["elev unknown"]["se"], 0)}). Their flag is +4.0% against floor 1. Their median error moves from {f(100 * ho["elev unknown"]["age"]["bias_median"], 1, True)}% to {f(100 * ho["elev unknown"]["floor"]["bias_median"], 1, True)}%, so the floor run predicts them a little too high, and their 90% coverage falls from {f(100 * ho["elev unknown"]["age"]["cover90"], 1)}% to {f(100 * ho["elev unknown"]["floor"]["cover90"], 1)}%.</p>
</section>

<section><h2>Floor curves</h2>
<p>Percent premium over floor 1 in the same building, posterior median with a 90% interval. Chain medians are listed so any disagreement between chains shows. A unit above floor 47 uses floor 47's column, and a walk-up unit above 6 uses floor 6's.</p>
<details open><summary>Elevator buildings</summary>{curves[0][1]}</details>
<details open><summary>Walk-ups</summary>{curves[1][1]}</details>
</section>

<section><h2>Gaussian process hyperparameters</h2>
<p>Prior: amplitude squared InvGamma(2, 0.04), so amplitude median {gpp["amp_median"]} with 90% from {gpp["amp_90"][0]} to {gpp["amp_90"][1]}. Lengthscale on log floor is log-normal with median {gpp["ls_median"]} and 90% from {gpp["ls_90"][0]} to {gpp["ls_90"][1]}. Nugget {gpp["nugget"]} amp².</p>
{table(["Group", "Quantity", "Median", "90%", "Chain medians", "R-hat", "ESS"], gprows, "num")}
</section>

<section><h2>Every column</h2>
<p>Share is the share of training ads with a nonzero value. Premium is 100(exp(β) − 1) with its 90% interval, next to the age run's value for the same column. Contribution is β² times the column's variance (β²p(1−p) for a 0/1 column), and for a curve the variance of the curve's value across ads. Sorted by contribution.</p>
{table(["Column", "Share %", "Premium", "Age run", "Contribution", "R-hat", "ESS"], frows)}
</section>

<section><h2>Variance before and after</h2>
<p>T is each ad's residual plus its building level plus the map, with each zone's mean removed: the part the features leave unexplained. Within-building variance is the residual variance after removing each building's mean residual. All on training ads, posterior means. Drops are in percent.</p>
{table(["Ads", "Count", "T age", "T floor", "T drop", "Resid age", "Resid floor", "Resid drop", "Within age", "Within floor", "Within drop"], vrows, "num")}
</section>

<section><h2>Building levels and the map</h2>
<p>Change in each building's level d (floor run minus age run), in percent, split by whether any of the building's training ads has a known floor.</p>
{table(["Buildings", "Count", "Mean change %", "SD change %", "Median |change| %", "SD d age", "SD d floor", "Correlation"], brows, "num")}
<p>The map surface barely moves: correlation {f(sc["corr"], 5)} across buildings, SD of the change {f(sc["sd_change"], 4)} against an SD of {f(sc["sd_age"], 3)}. Manhattan amplitude {f(sa["age"]["manhattan"][0], 3)} to {f(sa["floor"]["manhattan"][0], 3)}, outer {f(sa["age"]["outer"][0], 3)} to {f(sa["floor"]["outer"][0], 3)}.</p>
</section>

<section><h2>Predictions written before the fit</h2>
{table(["Prediction", "Result", "Verdict"], prows)}
</section>

<section><h2>Convergence</h2>
<p>Gate passed. Largest R-hat {f(cv["max_rhat"], 4)} and smallest ESS {f(cv["min_ess"], 0)}, both on <code>{cv["max_rhat_name"]}</code>, the outer-zone map amplitude.</p>
{table(["Quantity", "R-hat", "ESS"], [[f"<code>{E(n)}</code>", f(r, 4), f(e, 0)] for n, r, e in d["convergence_least_ess"]], "num")}
</section>
</main>
<script type="application/json" id="d">{json.dumps(d, separators=(",", ":"))}</script>
"""
open("floor-data.html", "w").write(page)
print(len(page))

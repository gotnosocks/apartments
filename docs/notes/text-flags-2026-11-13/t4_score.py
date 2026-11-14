"""Text flags, step 4: precision and recall of the old and new flags from the fresh sample.

I join the readers' labels of the fresh sample (`t3_eval.py`) to its key, drop the ads a
reader called unclear, and count them. Each part h of a flag's draw stands for N_h listings
of L1's dataset with a description, outside the development sample. With p_h the share of
its read ads the readers call "yes", I weight the parts back to the population:

- precision of a version is sum(N_h p_h) / sum(N_h) over the parts it marks;
- recall among listings with a mark or a candidate word is sum(N_h p_h) over the parts it
  marks, divided by sum(N_h p_h) over every part with a mark or a candidate word.

The draw of ads with no candidate word stands for about 1.8 million listings, and its 10 or
20 reads can't bound their share of true ads, so the recall leaves those listings out and I
print the draw's labels as a check. To show how much rests on that, I also give each recall
as it would be if 0.1% of the no-candidate listings were true. `rent_stabilized` keeps its
pattern, so its old and new versions are the same.

For an interval I take the variance of each estimate by the delta method, over the parts,
with p_h replaced by (yes + 1) / (read + 2) so a part with no "yes" still adds its
uncertainty, and with the finite-population correction. The effective sample size is
p(1 - p) / variance at that adjusted estimate, and the interval is Wilson's on it. I also
give the estimated count of true marks for each version and their ratio.

The scores go to `OUT/t4_scores.json`. Last I print the reader's evidence for each read ad
where a version and the reader disagree, and for each ad the reader found unclear.
"""

import json

import numpy as np
import pandas as pd
from common import OUT, READS, read_labels

Z = 1.959964
# A share of true ads among the no-candidate listings, for the recall's sensitivity.
CHECK_RATE = 0.001
CHECK = {"neither, no candidate", "unmarked, no candidate"}
MARKS = {
    "income_restricted": {"old": {"both", "old only"}, "new": {"both", "new only"}},
    "shared_space": {"old": {"both", "old only"}, "new": {"both", "new only"}},
    "rent_stabilized": {"old": {"old"}, "new": {"old"}},
}


def wilson(p, n):
    if not n > 0:
        return 0.0, 1.0
    d = 1 + Z**2 / n
    c = (p + Z**2 / (2 * n)) / d
    h = Z / d * np.sqrt(p * (1 - p) / n + Z**2 / (4 * n**2))
    return float(max(c - h, 0.0)), float(min(c + h, 1.0))


summary = json.loads((READS / "eval-summary.json").read_text())
lab = read_labels("eval")
print(f"fresh ads {len(lab)}, without a label {int(lab.label.isna().sum())}")
parts = []
for (flag, stratum), g in lab.groupby(["flag", "stratum"], sort=False):
    yes, no = int((g.label == "yes").sum()), int((g.label == "no").sum())
    parts.append(
        {
            "flag": flag,
            "stratum": stratum,
            "N": summary["strata_without_dev"][f"{flag}: {stratum}"],
            "drawn": len(g),
            "yes": yes,
            "no": no,
            "unclear": int((g.label == "unclear").sum()),
            "missing": int(g.label.isna().sum()),
        }
    )
parts = pd.DataFrame(parts)
parts["read"] = parts.yes + parts.no
parts["p"] = parts.yes / parts.read
parts["pt"] = (parts.yes + 1) / (parts.read + 2)
parts["v"] = parts.pt * (1 - parts.pt) / parts.read * (1 - parts.read / parts.N)
with pd.option_context("display.width", 200, "display.max_columns", 20):
    print(parts.drop(columns=["pt", "v"]).round(3).to_string(index=False))

scores = {"parts": parts.drop(columns=["pt", "v"]).to_dict("records")}
for flag, versions in MARKS.items():
    f = parts[parts.flag == flag]
    weigh = f[~f.stratum.isin(CHECK)]
    out = {}
    for version, marked in versions.items():
        on = f[f.stratum.isin(marked)]
        w = on.N.sum()
        prec, prec_t = (on.N * on.p).sum() / w, (on.N * on.pt).sum() / w
        var = (on.N**2 * on.v).sum() / w**2
        n_eff = prec_t * (1 - prec_t) / var
        c = weigh.stratum.isin(marked).to_numpy(float)
        a, b = (weigh.N * weigh.p * c).sum(), (weigh.N * weigh.p).sum()
        bt = (weigh.N * weigh.pt).sum()
        rec, rec_t = a / b, (weigh.N * weigh.pt * c).sum() / bt
        rvar = (weigh.N**2 * (c - rec_t) ** 2 * weigh.v).sum() / bt**2
        r_eff = rec_t * (1 - rec_t) / rvar
        out[version] = {
            "precision": float(prec),
            "precision_95": wilson(prec, n_eff),
            "precision_n_eff": float(n_eff),
            "recall": float(rec),
            "recall_95": wilson(rec, r_eff),
            "recall_n_eff": float(r_eff),
            "true_marks": float(a),
            "marked": int(w),
        }
    out["true_marks_new_over_old"] = out["new"]["true_marks"] / out["old"]["true_marks"]
    out["true_in_population"] = float(b)
    check = f[f.stratum.isin(CHECK)].iloc[0]
    out["check"] = {k: int(check[k]) for k in ("N", "drawn", "yes", "no", "unclear")}
    for version in versions:
        out[version]["recall_if_check_rate"] = float(
            out[version]["true_marks"] / (b + CHECK_RATE * check.N)
        )
    scores[flag] = out
    print(f"\n{flag}: about {b:,.0f} true listings outside the check draw")
    for version in versions:
        s = out[version]
        lo, hi = s["precision_95"]
        rlo, rhi = s["recall_95"]
        print(
            f"  {version}: marks {s['marked']:,}, precision {s['precision']:.3f}"
            f" ({lo:.3f} to {hi:.3f}, n_eff {s['precision_n_eff']:.0f}),"
            f" recall {s['recall']:.3f} ({rlo:.3f} to {rhi:.3f},"
            f" n_eff {s['recall_n_eff']:.0f}), true marks {s['true_marks']:,.0f},"
            f" recall at {CHECK_RATE:.1%} of the rest {s['recall_if_check_rate']:.3f}"
        )
    print(
        f"  true marks new / old {out['true_marks_new_over_old']:.2f}, check {out['check']}"
    )
(OUT / "t4_scores.json").write_text(json.dumps(scores, indent=2, default=float))

# The evidence of each read ad where a version and the reader disagree, and of the unclear.
print("\nDisagreements (flag | part | label | id | evidence):")
for flag, versions in MARKS.items():
    f = lab[lab.flag == flag]
    marked = f.stratum.isin(versions["old"] | versions["new"])
    show = (
        (marked & (f.label == "no"))
        | (~marked & (f.label == "yes"))
        | (f.label == "unclear")
    )
    for r in f[show].sort_values(["stratum", "label"]).itertuples():
        print(f"{flag} | {r.stratum} | {r.label} | {r.id} | {r.evidence}")

import pandas as pd, re

L = pd.read_parquet("levels_live.parquet")
B = pd.read_parquet("levels_back.parquet")
print(L.columns.tolist())
key = [c for c in L.columns if c in ("building", "name")][0]
u = set(L[L.rhat > 1.05][key]) | set(B[B.rhat > 1.05][key])
l = L.set_index(key)
b = B.set_index(key)
secs = [m.group(1) for m in re.finditer(r"^## (\S+)", open("texts.txt").read(), re.M)]
print(len(u), len(secs), sorted(u - set(secs)), sorted(set(secs) - u))
rows = []
for n in u:
    g = lambda d, c: d.loc[n, c] if n in d.index else float("nan")
    rows.append(
        (
            n,
            g(l, "rhat"),
            g(b, "rhat"),
            g(l, "level"),
            g(b, "level"),
            g(l, "c0"),
            g(l, "c1"),
            g(l, "n_train"),
            g(b, "n_train"),
            g(l, "n_held"),
            g(b, "n_held"),
        )
    )
d = pd.DataFrame(rows, columns="b rl rb ll lb c0 c1 nl nb hl hb".split())
d["mx"] = d[["rl", "rb"]].max(axis=1)
d = d.sort_values("mx", ascending=False)
d.to_csv("union.csv", index=False)
pd.set_option("display.width", 250)
pd.set_option("display.max_rows", 200)
print(d.round(2).to_string(index=False))

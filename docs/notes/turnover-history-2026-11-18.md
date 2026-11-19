# The turnover gradient on the held-out history: none, item closed (2026-11-18)

No fit and no money spent. Script and log are in `docs/notes/turnover-history-2026-11-18/`.

`docs/notes/turnover-low-asks-2026-11-18.md` left the rest of the turnover gradient as a
candidate mean term: on the 2025-11-10 backtest the mean gap ran from +0.021 in the lowest
turnover quartile to −0.008 in the highest. Before any fit, `hist.py` puts S13's bands on
the 189,647 held-out ads of the latest-split run `l2bt`, using the turnover columns of
`b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise-turnover` (every ad joined).

| Band | Ads | Mean gap (se, by building) | Below the 5% point | Above the 95% point |
|---|---|---|---|---|
| None | 10,301 | −0.0062 (0.0010) | 5.4% | 4.1% |
| Q1 | 37,893 | −0.0054 (0.0005) | 6.2% | 4.6% |
| Q2 | 43,795 | −0.0034 (0.0004) | 5.4% | 4.2% |
| Q3 | 45,534 | −0.0027 (0.0004) | 5.5% | 4.6% |
| Q4 | 47,584 | −0.0051 (0.0004) | 6.4% | 5.4% |
| Units unknown | 4,540 | −0.0029 (0.0016) | 6.9% | 6.2% |

The bands differ by at most 0.35 points and have no order: the lowest and highest quartiles
have the same gap. The same holds in each period (to 2019, 2020 to 2021, 2022 to 2023,
from 2024) and in both halves of the buildings. The one band that moves is buildings with
no other ad in two years, +0.017 in 2020 and 2021 and −0.022 in 2022 and 2023, which is
the market's swing in those years and no turnover effect.

So the backtest's gradient belongs to its sample. A backtest holds the ads open on one day
at their final asks, and ads that stay open are the slow ones; in a building where few
units come up, an ad open on a given day is more often one asking too much. A mean term
for turnover would fit that sample and has no support in the history. No fit is proposed.
High-turnover buildings do hold more low first asks, and the `raised` caution
(`docs/notes/raise-caution-2026-11-18.md`) covers the part that is raised later.

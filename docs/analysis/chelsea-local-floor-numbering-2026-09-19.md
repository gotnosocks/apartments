# Local unit-number mappings after conflict review

Four buildings support a limited interpolation hypothesis after reviewing their
own-apartment floor statements. This adds useful floor candidates, but **does not
increase the number of buildings supporting floor-by-elevator contrasts**. It
does not justify expanding the interaction model beyond the previously supported
low-floor thresholds.

| Building | Explicit floor versus label prefix | Reference units | Prefix range |
| --- | --- | ---: | --- |
| 152 West 20th | Prefix + 1 | 4 | 1–3 |
| 312 West 20th | Equal | 6 | 2–6 |
| 317 West 22nd | Equal | 8 | 3–5 |
| 350 West 18th | Equal | 5 | 2–6 |

The review covers 33 advertisements and all 46 associated captures. The unit
statements are explicit: for example, 152 West 20th's floor/flight descriptions
support the offset, while 350 West 18th distinguishes the building's six floors
from the apartment's own numbered floor. Media references were considered in
context. The artifact retains descriptions, exact text spans and source-label
capture hashes.

The exploratory rule requires four distinct reference units, two prefix levels,
and a consistent offset. Unreviewed comparable disagreements remain vetoes.
Buildings with previously reviewed numbering problems or unreliable scope remain
excluded, even after those floor values are masked. This avoids selecting only
agreeing evidence and then declaring a numbering rule reliable.

Whole-unit checks remove every advertisement for a held-out apartment. With at
least three other reference units and two prefix levels, **19 held-out units
agree**; **four are outside the remaining units' prefix range**, so the rule
abstains. These are selected-rule consistency checks, not an unbiased accuracy
estimate: the buildings were selected after inspecting their reference patterns,
and repeated broker copy may share errors across units.

Within each building's observed prefix range, the mappings supply candidates for
100 otherwise unknown-floor observations covering 39 units. Twenty of those units
already have explicit-floor reference evidence on another advertisement; only
**19 units lack such reference evidence**. No claim is made about a historical
renumbering date or physical floor height, and these candidates have not been
written into analytical data or fitted.

The support comparison first withholds the 17 previously reviewed floor claims,
then adds these local candidates to missing-floor rows only:

| Elevator evidence | Explicit-floor rows / units | With candidates, rows / units |
| --- | ---: | ---: |
| No elevator | 111 / 84 | 129 / 93 |
| Elevator | 122 / 97 | 136 / 99 |
| Unknown | 114 / 95 | 182 / 120 |

Most extra rows still lack elevator evidence. At thresholds 2, 3, 4 and 5,
walk-up buildings with observations on both sides remain **7, 10, 10, 1**;
elevator buildings remain **3, 5, 6, 6**. The candidate mappings add no such
buildings. Consequently, the next interaction experiment should use the reviewed
explicit floor baseline and test a small number of supported contrasts; this
label calibration is a possible sensitivity analysis, not a reason to expand
the main model's floor range or claim stronger independent support.

This audit uses the frozen 52,704-row source cohort, not the refreshed cohort with
172 current listings. It preserves literal unit labels and does not transfer a
building rule automatically to newly captured listings.

Artifact: `data/model/chelsea-floor-label-calibration-20260919`.
Reproduce with `PYTHONPATH=. UV_CACHE_DIR=/tmp/apartments-uv-cache uv run --frozen
--no-sync python docs/analysis/scripts/review_floor_label_calibration.py`.
Four tests cover whole-unit exclusion, repeated-advertisement support inflation,
conflict vetoes and interpolation-only candidates.

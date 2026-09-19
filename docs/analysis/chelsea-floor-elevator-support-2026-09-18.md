# Floor × elevator: support before fitting

The frozen 52,704-row cohort supports a limited explicit-floor interaction
experiment, rather than an unrestricted interaction at every floor threshold.
The audit uses the existing model's normalization and keeps unknown elevator
status separate from an explicit no-elevator claim.

| Elevator evidence | Rows with known floor | Distinct units | Buildings | Floor labels observed |
| --- | ---: | ---: | ---: | --- |
| No elevator | 112 | 85 | 48 | 2–6 |
| Elevator | 125 | 100 | 54 | 2–11, 14–17, 20, 24, 28, 41 |
| Unknown | 127 | 101 | 52 | 1–5 |

Only thresholds **2, 3, 4 and 5** have observations on both sides in both known
elevator groups. Even there, support within buildings is sparse:

| Threshold `k` in `1(floor > k)` | No-elevator buildings with floors on both sides | Elevator buildings with floors on both sides |
| --- | ---: | ---: |
| 2 | 7 | 3 |
| 3 | 10 | 6 |
| 4 | 10 | 7 |
| 5 | 1 | 7 |

These are threshold comparisons, not necessarily adjacent-floor comparisons.
The last row depends on only one no-elevator building. Unit counts can overlap
between categories when source claims vary; repeated captures/months are not
independent apartment evidence.

At every observed threshold from **6 upward**, the naive product
`has_elevator * 1(floor > k)` duplicates the floor main-effect column exactly:
all observations above those thresholds have elevator evidence. Adding these
13 interactions cannot separately identify the proposed coefficients. A prior
could allocate their combined contribution, but would not create missing support.
Threshold 1 also lacks observed lower-floor cases with known elevator status.

The unvalidated unit-label candidates provide much wider apparent coverage:
1,371 rows / 785 units with no-elevator evidence and 22,620 rows / 8,274 units
with elevator evidence. However, inferred labels in the no-elevator group extend
to **62**. This is a warning about interpreting unit-number prefixes, not evidence
of a 62nd-floor walk-up. The earlier [label audit](chelsea-unit-label-floor-2026-09-18.md)
already documents multi-digit numbering and systematic offsets. More apparent
overlap does not justify using these candidates before validating their meaning.

Across the full cohort, **43 buildings** have both positive and negative elevator
claims. This audit does not determine whether those are temporal changes, separate
access arrangements, scope errors or incorrect data. They require source review
before treating elevator status as a fixed building characteristic.

The next experiment should use a reviewed floor metric, preserve both missingness
states, and restrict candidate interactions to supported contrasts. Compare joint
floor contrasts, group offsets and residual patterns under matched priors; examine
whether fewer interaction coefficients suffice. Within-building overlap alone
does not establish comparable apartment quality or causal effects.

Artifact: `data/model/chelsea-floor-elevator-support-20260918`. The source cohort
and label-audit hashes are verified, and explicit claims and inferred candidates
are reported separately. Four tests cover distinct-unit counting, unknown status,
within-building support and conflicting elevator claims. No model input or fit
changed.

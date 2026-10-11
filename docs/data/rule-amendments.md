# Data rules amended in place

A data rule's file normally never changes: a change is a new version (`quarantine-v12`
after `quarantine-v11`), so every fit's rows can be rebuilt from its record. Ben may
choose instead to amend a rule in place, so that the fits already run on it stay
current. Each such amendment is listed here. The file as it stood before stays in the
repo, `data.RULE_AMENDMENTS` maps the hash a run recorded for it to a rule that
applies it, and `data.recorded_rules` rebuilds each run's own rows, so a fit's
posterior always matches the units it was fit on. Fits on either side of an amendment
carry the same rule name and are compared as the same data; the rows below are the
difference between them.

## unit-reviews-v1, 2026-10-11

- **Decision:** Ben, on PR #687 (2026-10-11): "Could we merge it and treat it as the
  same dataset? it's only one building". The amendment was first proposed as
  `unit-reviews-v2`.
- **Change:** `config/reviews/unit-joins-20261011.jsonl` is
  `unit-joins-20261007.jsonl` (sha256 `a3f9630b…66c2`) with one group appended: at
  21 West 12th Street, units 2, 2B, 2F and 2R are one apartment, the second floor's
  rear one-bedroom with a 400 sq ft terrace, by its ad text (the evidence is in the
  file's line).
- **Rows:** the apartment has 5 listing rows in the NB8 dataset: the four 2022
  listings (2B, 2, 2R, 2F) and 2B's 2025 listing. 4 of them change unit id (2R already
  had the group's smallest), four unit ids become one, and no row is dropped or moves
  between training and held-out on the latest split. On the current rules NB8 has
  91,906 units, not 91,909.
- **Fits:** fits started before the merge saw the four unit ids (they recorded the
  hash `a3f9630b…66c2` and rebuild with `unit-reviews-v1@20261007`). Fits started
  after it see one.

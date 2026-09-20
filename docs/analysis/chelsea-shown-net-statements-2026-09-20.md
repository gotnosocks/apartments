# Explicit shown-net rent statement extraction

The rent-basis measurement now recognizes literal statements such as “Net
effective price shown,” “Net Rent Shown” and “Rent advertised is net effective.”
Version 6 extends statement recognition only. It does not compute concessions,
infer gross prices, change the analytical target or certify historical terms.

The reviewed advertisements 2834394, 2560481, 2362330, 2967520 and 4982803 all
gain the expected statement signal. Their existing gross quotes, where present,
remain separate literal amounts. Missing net amounts remain missing, even when
concession arithmetic happens to match an advertised price.

## Validation and captured-data replay

All 71 focused measurement, own-price-review and advertised-net-review tests
pass. Coverage includes sentence order, exact offsets, negation, administrative
context, unrelated uses of “shown,” preservation of gross quotes and absence
of invented net amounts. The initial test invocation needed `python -m pytest`
to resolve repository modules; a new sentence-order test then exposed a missing
“is” connector, which was fixed before the passing run.

An exact comparison against the saved v5 implementation from commit `26381ba6`
checked all 71,813 attached captures in the original expanded-floor source;
252 out-of-cohort evidence records were skipped. Statement measurements changed
in 1,257 captures across 1,023 ads. All nonstatement measurements, including
quoted amounts and analytical-target matches, were identical. This replay is
a scope/regression check, not a manual precision audit of every new match.

The largest added literal form is “rent advertised is net effective” (851
occurrences). The added statements include 122 occurrences with administrative
language in their context and none flagged as preceded by negation. Existing
context flags remain intact; these counts do not authorize cohort exclusions
or a historical gross/net assignment.

The reproducible replay helper is
`docs/analysis/scripts/replay_shown_net_statements.py`. Its artifact,
`data/model/chelsea-shown-net-statement-replay-20260920`, saves both measurement
implementations, full changed captures and analytical rows, and input bindings.
Manifest: `ad2c18f00501eeb74bb5700d120080e6442473bf400c1cd992f400a41a85752b`.
Publication and full bundle hash verification passed. The ongoing scope refit's
frozen dataset and model specification are unaffected.

The same measurement has passed the existing full source audit on the cumulative
nine-ad source (session 14173, exit 0). The published output is
`data/model/chelsea-commercial-scope-rent-basis-audit-20260920`; independent
bundle hash verification also passed. It covers 71,797 captures on 52,644 rows
and flags 2,806 observations (2,199 units): 959 advertised-net statements without
a target-amount match, two exact-net-only matches across all attached captures,
101 explicit gross matches, 1,649 other net mentions and 95 other labelled
amounts. All 14 flagged capture-time active rows fall in the other-net-mention
category. These are evidence-review priorities, not automatic
historical price-basis labels or exclusions. The fixed residual-review wording
also now describes the target as recorded advertised asks rather than implying
every target is independently verified base/gross rent.

## Exact net-price matches requiring residual context

The refreshed audit retains two observations for which all attached captures
explicitly quote the analytical amount as net. These are not new consequences
of v6: the full replay established that amount matches did not change.

- Advertisement **3116129**, 111 West 16th Street #1G: the description says
  `1999.00 is the NET EFFECTIVE rent` and describes a 14-month lease with
  13 payments of $2,152. Its single raw capture (74104) has an own-ad ACTIVE
  event on July 9, 2020 and DELISTED event on July 16, both $1,999. The lease
  arithmetic is approximately $1,998.29 per month, close but not identical to
  the literal $1,999 quote. Preserve the explicit quote and payment schedule
  separately; do not “correct” rounding or invent a signed-lease amount.
- Advertisement **3193768**: both raw captures (37620, 104243) have matching
  own-ad ACTIVE and NO_LONGER_AVAILABLE events on August 27, 2020 at $2,379.
  Both descriptions distinguish $2,595 monthly rent from $2,379 net monthly
  cost. Its structured 340 West 17th Street #2A address conflicts with the
  description's 344 West 17th Street, as documented in the
  [earlier access review](chelsea-floor-access-conflicts-2026-09-19.md).

All three raw payloads were reloaded from the frozen granular archive and
checked against the audit's raw SHA-256 witnesses before inspecting their own
advertisement histories. The descriptions were captured in September 2026;
they do not supply verified historical concession effective dates. Their exact
source rows, complete descriptions, capture hashes and literal measurements are
preserved in the published audit (manifest
`41e15e674d4c8666da5e8e9805618750b8c76dfce89cea272a4cab1877a9f8ec`).
These findings should accompany interpretation of their residuals and motivate
a separate price-basis sensitivity; neither numerical replacement nor a new
source exclusion has been applied.

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

The same measurement is now being applied through the existing full source
audit to the cumulative nine-ad source. Output is planned at
`data/model/chelsea-commercial-scope-rent-basis-audit-20260920`; publication
remains pending. This produces evidence-review priorities, not automatic
historical price-basis labels or exclusions. The fixed residual-review wording
also now describes the target as recorded advertised asks rather than implying
every target is independently verified base/gross rent.

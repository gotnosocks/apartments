# Literal price-basis review and source revision

The full accepted Chelsea cohort was screened independently of fitted residuals:
**52,863 observations, 72,065 attached captures, 71,730 available descriptions**.
The final experimental parser preserves exact character spans and distinguishes
quoted net, gross and legal amounts, negation, administrative context, and
statements about the advertised price. It never computes a missing gross rent.

The final v4 screen produces 3,015 candidate observations. Of these, 164 have an
analytical target matching an explicit net quote in every attached capture;
101 match an explicit gross quote, and 89 have an advertised-net statement
without a matching target amount. The other 2,661 cases are broader mentions or
other labelled amounts. These categories describe textual evidence, not verified
economic terms at the historical target date.

All 14 current cases are mentions in approval-standard boilerplate. Every matched
mention has administrative context and preceding negation. No current listing
is recommended for exclusion by this review.

## Original-price checks and manual review

The v3 review packet contains 259 prioritized historical observations and all
312 attached captures: explicit target-net matches plus affirmative
advertised-net statements, including gross-target counterexamples. Original
listing and event shards are hash-verified. Every capture's earliest own rental
ACTIVE event agrees with its analytical date label and target. Price-change
timestamps remain separate. For example, ad 1599722 has earlier August price
changes but an October ACTIVE event; the first price-change timestamp is not
silently substituted for the model's event-date contract.

The extracted target-quote contexts for all 165 v3 high-priority observations
were reviewed. Full descriptions were inspected for specific exceptions:

- **2532848:** target $4,500 explicitly gross, separate $4,250 net offer. Retain.
  The parser initially attached the following Net label to the gross amount.
- **2623722:** $6,000 is called net versus $6,500 gross, with a broker-fee/tenant
  free-rent tradeoff. Do not turn that conditional offer into an assumed discount.
- **2311395:** separate net offers of $4,453 and $4,618 for different lease terms,
  versus stated $5,195 gross. Keep the alternatives distinct.
- **2902349:** $3,333 net quote with inconsistent or alternative six-month and
  15–18-month offer wording. Do not infer one applicable term.

The closed review recommends **164 unresolved gross-basis exclusions**, retaining
2532848. Every proposal retains literal evidence from every capture and original
pricing/event evidence, and validates against its unchanged parent row. This is
not a claim that the later-captured concession was applicable at the initial date.
It is a decision to keep unresolved price bases outside the gross-ask cohort.
The other 94 packet cases remain pending; a blanket exclusion based on “net
effective advertised” would discard some targets matching an explicit gross quote.

These 164 observations are concentrated in Chelsea Tower (66), The Arthur (24),
and The Grove (22), and date from 2015–2020. Structured `netEffectiveRent`,
`monthsFree`, and `leaseTermMonths` are null throughout this selected group.
This is a source of possible building/time effects, not an estimated amenity
contribution. It requires a new fit before drawing pricing conclusions.

## Measurement failures are retained in the audit trail

The initial v1 scan reported 173 exact net matches and one apparent net/gross
conflict. Manual inspection exposed adjoining-quote errors: a following label
could relabel the previous number, including across a newline or inside a
parenthetical alternative offer. V2/v3 progressively corrected those rules;
v4 adds the reviewed “Gross Price per month” construction. The final count is
164. Earlier artifacts are preserved and superseded, not rewritten.

The 37 measurement and original-price packet tests include these regressions,
negative/administrative language, exact spans, decimal amounts, multiple capture
consensus, event-date boundaries and raw/shard tampering. Together with the
existing quarantine tests, **67 tests pass**. Development cases are not an
independent accuracy evaluation. These bounded patterns can still miss complex
or dollar-sign-free quotes; they do not replace source review.

## Candidate publication

The combined decision bundle contains the 164 reviewed net-basis decisions plus
the previously reviewed short-term ad **970866**. Ad **2675026** overlaps the
earlier two-ad review and appears only once. Original review records, clocks,
and their hashes are preserved when composing the new decision bundle.

The new candidate is `chelsea-reviewed-net-and-scope-analysis-20260919`. The
published cohort has **52,698 rows, 22,163 units, 1,130 buildings and all 172
current listings**. Twenty-six units and one building lose their only included
historical observations; they are not silently retained as empty model groups. The
projection reconstructs the exact ordered parent from retained rows and the
hashed exclusion sidecar. It changes no retained fields or current observations
and substitutes no prices. Actual publication and identical full-cohort replay
both pass. The earlier two-ad candidate is preserved, but the
combined source revision should be used for the next source-sensitivity fit.
The selected model and the live controlled laundry experiment remain unchanged.

Important artifacts under `data/model/`:

- `chelsea-literal-rent-basis-audit-v4-20260919`: final complete-cohort screen.
- `chelsea-rent-basis-own-price-review-v3-20260919`: original-price packet used
  for the closed manual review, including the retained false-positive case.
- `chelsea-reviewed-net-quote-recommendations-20260919`: 165 findings / 164 proposals.
- `chelsea-reviewed-net-and-scope-decisions-20260919`: composed 165 decisions.
- `chelsea-reviewed-net-and-scope-analysis-20260919`: combined candidate source.

Next validate the combined source with the isolated readers and a fresh graph
proof, then refit. Its unit/building membership differs from the accepted fit;
comparisons must report removed groups and compare residuals on common rows.
Do not reuse the numerical proof for the earlier two-ad candidate, or claim
identical priors without checking changed normalization and group constraints.

# Remaining net-rent wording: source review queue

The floor-description review found advertisement **2438307**, whose description
says “Net effective price listed.” The earlier price-basis screen recognizes
positive statements with “listed” or “advertised” before the price/net wording;
this reversed order is outside its frozen rule. The earlier exclusion of 503
observations remains correct for its reviewed scope, but does not establish that
all remaining historical prices have a resolved gross basis.

An offline, hash-verified pass over every description supporting the current
52,704-row research cohort finds **3,042 captures / 2,429 observations / 1,894
units** mentioning net-effective rent. None matches the earlier positive-form
screen. A narrower reversed-order pattern (`net effective rent/price
listed/advertised`) matches **114 captures / 96 observations**. These are review
candidates, not automatic exclusions or a prevalence estimate of net-priced
model targets. Statements can supply both gross and net amounts, describe other
terms, or postdate the initial price event used by the historical model.

The single current observation in the broad screen is Ruby advertisement
5157053. Its wording says approval standards use gross rent rather than net
rent; it does not say the advertised price is net. No current observation
matches the narrow reversed-order statement. A broad keyword rule would thus
misclassify at least the meaning of this current example.

For the motivating advertisement, original capture 106426 has a verified own
listing price history beginning at **$3,860 on June 28, 2018**, matching the
analytical target, and ending at **$3,593 on August 5, 2018**. Structured
`netEffectiveRent`, `monthsFree` and `leaseTermMonths` are null. The recovered
same-advertisement description mentions half a month free, but was captured in
2026; it does not establish the gross basis or concession terms of the initial
2018 ask. Do not replace $3,860 with a computed gross rent or the later $3,593.
This remains an unresolved price-basis case for a subsequent reviewed overlay.

The next source-review batch should adjudicate the 96 narrow candidates, inspect
all available own-advertisement pricing/concession evidence, and compare gross
versus net terms at the relevant event clock. Expand the broader screen with
varied sentence forms and negative cases. Preserve missing lease terms and dates
rather than manufacturing a conversion. Publish any membership decisions as a
new immutable source revision and refit before using that revised cohort.

No source values, cohort membership, selected model or running fit inputs changed
in this audit. The current source and floor experiments retain their identical
frozen cohort for a representation comparison; these unresolved source issues
limit interpretation and remain separate from sampling convergence.

Artifacts:

- `data/model/chelsea-remaining-net-rent-wording-20260918`: all candidate text,
  literal spans, clocks and source hashes; frozen screen and source bindings.
- `data/model/chelsea-floor-net-rent-capture-review-20260918`: verified original
  address and complete own-listing pricing for capture 106426.
- `data/model/chelsea-floor-description-adjudication-20260918`: the source review
  that prompted this follow-up.

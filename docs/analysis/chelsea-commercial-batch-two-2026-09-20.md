# Further commercial-screen review and rent-basis leads

The next eight unreviewed full descriptions in hash order contain incidental
commercial references: five shared-amenity descriptions, one commercial laundry
appliance and two residential home-office uses. None supports a scope exclusion.
This ordering is reproducible but is not a representative sample or a ranking
of likely data errors. Across the completed batches, 498 groups remain unreviewed.

Four descriptions from The Chelsea explicitly quote gross rent and concessions.
Their analytical rows use historical initial advertised asks:

| Advertisement | Historical price date | Analytical ask | Captured gross quote | Captured concession |
| --- | --- | ---: | ---: | --- |
| 2834394 | 2019-08-06 | $8,375 | $9,110 | Six weeks free over 12 months |
| 2560481 | 2018-10-23 | $6,857 | $7,569 | One month free over 12 months |
| 2362330 | 2018-04-13 | $4,500 | $5,225 | One month free; term unspecified |
| 2967520 | 2020-01-27 | $7,000 | $7,500 | One month free over 15 months |

For 2967520, $7,500 × 14/15 equals the analytical $7,000. This is evidence to
investigate a net-effective price basis, not proof that the later-captured
concession applied at the initial event. For 2560481, the analogous arithmetic
gives $6,938.25, not $6,857; a uniform conversion would conceal the discrepancy.
Descriptions were captured in September 2026. Retain their capture clocks and
inspect the own-ad price histories before assigning historical gross/net terms.
No asking rent, concession field or model target was changed in this review.

The descriptions also reinforce scope boundaries: a shared fifteenth-floor
terrace does not locate an apartment, and some amenities are explicitly
“coming soon.” Advertisement 2531860 independently describes the fifth floor,
consistent with the existing label-derived floor 5. Advertisement 2390850
describes a den usable as a bedroom or office; it does not settle bedroom count.

## Reproduction

`docs/analysis/scripts/review_commercial_batch_two.py` binds the exact group and
screen manifests, preserves complete descriptions and associations, checks
analytical row hashes, and publishes literal review spans plus four full
source/evidence cases for price-basis follow-up. Its artifact is
`data/model/chelsea-commercial-manual-batch-two-20260920`. Publication, identical
replay and full artifact hash verification passed. These checks reproduce a
manual review; they do not validate a general commercial-use classifier.

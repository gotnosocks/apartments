# Laundry location: measurement review before a four-level fit

The accepted Bayesian model distinguishes recorded in-building and in-unit
laundry, plus unknown reporting. It does not yet distinguish no laundry or
shared laundry on the apartment's floor. An offline pass over all descriptions
supporting the frozen 52,704-row cohort now identifies evidence for that work.

| Phrase family | Observations | Units | Buildings |
| --- | ---: | ---: | ---: |
| Laundry on each/every floor | 251 | 140 | 13 |
| Same-floor wording | 31 | 25 | 10 |
| On the/your floor | 40 | 32 | 13 |
| Down/across the hall | 9 | 8 | 7 |
| No laundry | 135 | 101 | 58 |
| Washer/dryer hookups | 40 | 35 | 17 |

Families can overlap and must not be added. The full screen contains 724 captures
and 504 observations. These are lexical candidates, not validated model values.
All source descriptions, exact spans, source clocks and hashes are preserved.

A building-diverse development review of 36 selected cases finds 20 shared
on-floor claims, two locations inside the apartment, two hallway descriptions
that concern another facility, six hookup-only claims, five denials of building
laundry and one unqualified no-laundry statement. This selected sample does not
estimate extraction accuracy or recall.

Important distinctions for the next measurement version:

- “Across the hall” can refer to the apartment's own laundry nook, a shared
  building laundry room, a roof deck or a storage room. Nearby words are not
  enough to assign shared on-floor laundry.
- In-unit and shared on-floor equipment can coexist. One reviewed description
  has a private washer and full shared laundry down the hall; it does not
  establish an in-unit dryer. Another explicitly offers additional floor machines.
- All six reviewed hookup-only examples currently carry an in-unit category.
  This is a source-composition review question: inspect structured amenity claims
  and other evidence before deciding whether installed equipment is established.
  One explicitly says the tenant can install equipment. Hookups alone are not
  installed laundry.
- Keep the scope of absence claims. A denial of building laundry and a denial of
  all on-site laundry are not automatically equivalent; unknown is never no
  laundry. Review contradictions and coexisting facilities explicitly.
- “Each/every floor” claims can establish shared floor access without inferring
  an apartment floor from its unit label. A named laundry-room floor alone cannot.

Before a four-level comparison, publish a reviewed measurement policy and
validate on different units, retaining separate claims where facilities coexist.
Then fit the matched Bayesian candidate and report joint category contrasts,
unit/building overlap, prior sensitivity and residual changes. A convenience
ordering does not require imposing positive coefficient increments. Existing
laundry estimates remain associations between the older recorded categories.

Additional source-review cases emerged: advertisement 3767178 names 191 Ninth
Avenue while its source building is 161 Ninth Avenue; advertisement 1271335 has
hookup/tenant-installation language plus employee/live-work wording. Neither was
corrected or excluded from this phrase audit.

Artifacts:

- `data/model/chelsea-laundry-location-phrase-audit-20260918`: complete candidate
  inventory, six phrase families, deterministic review sample and frozen script.
- `data/model/chelsea-laundry-location-adjudication-20260918`: all 36 review
  decisions, supporting spans, source bindings and frozen publisher.

No analytical values, cohort membership or model inputs changed in this audit.

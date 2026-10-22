# PLUTO-as-of: what it changes and what the result means

*Modeling, 2026-10-08. Sources: PR #439 (v1), PR #502 (v2), `frontier/src/rentfrontier/features.py` (`pluto_v1`, `dated_alterations`), `docs/model/feature-tests.md`, `docs/model/research-backlog.md` item 3, `docs/handoff/data-improvements.md` (repo at d7445a0).*

## What the served model reads from PLUTO today
MapPLUTO is the city's lot database. DCP publishes a new release each year, starting in spring. For each listing's building, the served model reads these fields from **today's** release:

- year built (as an era: pre-1900, 1900–29, …)
- floors, residential units, residential floor area per unit, built FAR
- building class family (C walk-up, D elevator, R condo, S mixed, other)
- flood zone 2015
- "altered since 2000", from the two recorded alteration years (`yearalter1/2`)

Two of these are already dated to the listing. Landmark and historic district come from LPC designation dates. "Altered since 2000" counts a recorded alteration only if its year is before the listing's year. Everything else is today's value, even for a 2010 ad.

## v1 (PR #439): every PLUTO field as the release of the year before the listing
**Which release.** Not the day before. The data folder holds only the first release of each year (09v1 through 26v1), and no publication dates. So a listing in year Y reads the first release of year Y−1. A November 2018 ad reads 17v1 (spring 2017), even though 18v1 was already out by then, so the values are about 18 months staler than they need to be, and up to about two years in the worst case. Reading "the latest release before the ad's date" is possible, but Data would first need every release of each year (v1–v3) and the date each was published.

**Result.** One Modal full fit on all 121,911 rows. It passed the gate (R-hat 1.0043, ESS 805) but scored **−71.1 ± 20.4** PSIS-LOO against the served model, a clear loss.

## What "revision noise" means
A building's PLUTO values change between releases for two very different reasons:

1. **The building changed.** It was built, converted or enlarged. Then the old release is the right value for an old ad, and today's value is a leak.
2. **DCP re-estimated the same building.** It corrected a unit count, re-measured floor area or reclassified the building, with nothing built. Then today's value is simply the better measurement, and the old release is just a worse one.

Most of the differences are case 2 (counts below). The research backlog shows the scale: against the 2010 release, residential units differ on 19.8% of rows and class on 10.5%, while the earlier unit-count audit found only about 1% with a real change. So most of what v1 swapped in was case 2. These are older, worse estimates of buildings that didn't change. That is "revision noise", and it is why v1 scores lower.

## Real examples
**15 Seventh Avenue South** (built 1900, no alteration on record). What each release says:

| Releases | residential units | residential floor area | floors | built FAR |
|---|---|---|---|---|
| 2009–2015 | 37 | 19,744 sq ft | 2 | 3.77 |
| 2016–2019 | 38 | 21,823 sq ft | 2 | 3.77 |
| 2020–2026 (today) | 36 | 21,823 sq ft | 6 | 3.77 |

Nothing was built. A two-floor building can't have a FAR of 3.77, so "2 floors" was a data error that the 2020 release fixed, and the unit count moved 37 → 38 → 36 as DCP re-counted.

- **Before (served model):** every ad in this building, from 2010 or 2024, sees 36 units, 21,823 sq ft and 6 floors. Those are the best values PLUTO has.
- **After v1:** a 2018 ad reads 17v1 and is told 38 units and 2 floors. A 2012 ad is told 37 units, 19,744 sq ft and 2 floors. The model now sees the same unchanged building as a low walk-up in some years and a six-floor building in others, and has to explain rents with values that were wrong.
- **After v2:** size and floors stay today's for every ad. Only the alteration years would come from the old release, and this building has none.

**51 Carmine Street** shows the smaller, common version: 15 units in the 2021 release, 14 in 2022, 13 in 2023, with no alteration since 1987.

**How often.** Across 135,759 rows, the dated release gives a different unit count on about 10% of rows and a different floor area or FAR on about 8%. Of those differences, only about 1% are ads from before the building existed, and 2–3% are buildings actually altered after that release. The rest are re-estimates like the two above.

## v2 (PR #502, merged 2b2d262): only the alteration years as of the listing
Size and class stay today's, because they are mostly re-estimates. Only `yearalter1/2` come from the year-before release, and never from a release older than the building. This changes "altered since 2000" on 3,137 rows.

The served model already ignores alterations dated after the listing's year, so v2 only matters where the *recorded* years changed between releases. For example, PLUTO keeps just two slots, so a third alteration can overwrite an older one. A record can also be added or corrected later. **Expected effect: small.** v2 is queued as one full fit on the current rules.

## My read
- **v1 should not be served.** Its loss comes from swapping good measurements for older, worse ones, not from removing a leak.
- **The leak in the served model is narrow.** It covers buildings that physically changed after an ad (case 1, a few percent of the rows whose values differ), plus the 2010s alterations PLUTO no longer lists.
- **A better design than either version:** keep today's values by default, and use the dated value only where the building actually changed, such as a new building, a K→D or G→D conversion, or a unit count that jumps with a permit. That fixes the real leak without importing revision noise. Data's DOB permit features (#437) date alterations directly and would serve the same purpose.
- **v2 decision:** serve it if it gains or is within noise. A clear loss would point to old alteration records being wrong.

# Housing economist review (reviewer subagent, 2026-10-22)

**Recommendation: Major revision.** The empirical engineering and the honest audit are strong. But the paper's main claim is about what features are "worth", and that claim rests on asking rents from a selected flow of listings, uses hedonic coefficients held fixed over 16 years, and gives no serious account of what the unit and building coefficients pick up.

## Main weaknesses

1. **The sample and outcome don't support claims about value.** The data are a flow of StreetEasy ads, which over-represent units that turn over often and market-rate units. The "last ask net of concessions" is chosen by time on market, since it is the price after any cuts. Stabilization is taken from the ad's own wording, which under-reports it, and asks for stabilized units mix legal and preferential rents. StreetEasy's coverage of Brooklyn also grows a lot after 2010. *Fix:* reweight to the housing stock (NYCHVS/ACS) and compare against NYCHVS contract rents. Model or report results by days on market. Estimate everything separately by stabilization status, and before and after HSTPA 2019.
2. **The coefficients are held constant from 2010 to 2026.** Implicit prices move. COVID plausibly shifted the value of laundry, outdoor space and doormen, and HSTPA changed what a stabilized unit is. *Fix:* let the key coefficients vary by period, at least pre-2020, 2020–21 and post-2021, and report how they drift.
3. **"Worth" is the wrong word.** Rosen-style gradients are equilibrium price differentials, not willingness to pay. Calling the 15% doorman premium "worth" credits the doorman with all the building quality that goes with one. The within-building floor premium bundles views, light, noise and the more expensive layouts on high floors. Laundry and dishwasher almost certainly stand in for renovation, which the Mundlak term cannot remove because renovations happen unit by unit within a building. *Fix:* reframe the title and abstract as "asking-rent differentials". You already have unit labels, so use repeat ads of the same unit (unit fixed effects, in the style of a repeat-rent index) to identify amenities from changes within a unit. Add controls taken from the ad text ("renovated", "views", exposure).
4. **The location result is framed as a prediction question when it is a capitalization question.** A flexible GP surface will absorb any smooth amenity, so finding that distances "relabel" the surface is expected and says nothing about whether parks are capitalized into rents. Park frontage fails your own permutation test and still appears in the abstract. Waterfront rests on 42 held-out buildings. *Fix:* separate the two questions. For value, use sharp contrasts such as frontage, blocks across a boundary, and differences across the street. Drop park frontage from the abstract until it passes the test you set.
5. **Building-level estimates.** The doorman, condo and gym estimates come from comparisons between buildings with no source of exogenous variation. Condo units are rented by individual owners and differ systematically from rental buildings. *Fix:* present these as descriptive conditional means and drop any language about value.

## Literature to engage

- Epple (1987, JPE), on identifying demand from hedonic prices.
- Sirmans, Macpherson and Zietz (2005, J. Real Estate Literature) and Malpezzi (2003), for benchmark coefficients.
- Kuminoff, Smith and Timmins (2013, JEL), on sorting and capitalization.
- Liu, Rosenthal and Strange (2018, JUE), "The vertical city", and Danton and Himbert (2018, JUE), on residential vertical rent curves.
- Ambrose, Coulson and Yoshida (2015, REStat), the repeat-rent index.
- Glaeser and Luttmer (2003, AER), Autor, Palmer and Pathak (2014, JPE), and Diamond, McQuade and Qian (2019, AER), on rent regulation.
- Black (1999, QJE) and Bayer, Ferreira and McMillan (2007, JPE), on boundary designs for location amenities.

## Strengths

- The floor curve that depends on whether the building has an elevator is new for residential NYC rents. It is cleanly identified within buildings and is a large, well-validated gain in forecasting.
- The simulation audit is unusually candid. It shows the random-effects bias in the unit coefficients and coefficient intervals that are too narrow, and the paper says plainly that coefficient intervals are not to be trusted.

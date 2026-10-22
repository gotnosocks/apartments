# Midtown West capture and "available now" (restated in the style guide)

I moved no files and changed nothing on the site.

## Midtown West capture

If Data collection moved the capture into archive/current-listings/ now, the next site build would price none of its 468 ads and show none of them. Nothing would break.

- The build gives each capture listing the neighbourhood recorded for its building in the site database, then prices it with the served fit's terms for that building. When a listing's building is missing from the fit, the build skips the listing and adds it to a count in build.json under "building not in the served fit". Skipped listings stay off every page, so they don't show as "no estimate" either.
- I compared the capture's 187 buildings against the live build. All 187 are missing from the NB8 fit's 5,415 buildings and from the site's building table. Both sides use StreetEasy building slugs, so I'm confident the buildings are absent and the IDs line up.
- The neighbourhood selector, the map, /best, the counts and the "available now" note each read their list of areas from the build. With no Midtown West buildings in the build, those pages would carry on with the eight current areas. The capture path doesn't depend on a hard-coded list of areas. summary.py and story.py do keep lists of fit inputs and design labels, and those would need Midtown West entries once a fit includes the area.
- Area names come from the dataset. Data improvements' held branch, data/nb9-midtown-west, splits Midtown West into Hell's Kitchen (1,116 buildings) and Hudson Yards (234 buildings), so the site would list those two names.

Recommendation: keep the capture out of archive/current-listings/ for now. Midtown West listings can appear on the site after a served fit includes its buildings. The nb9 branch would do that. It is held for your opt-in, and it still needs unit-label merges, a quarantine and price-screen read, and a riverparks twin. A fit reading this capture would price its ads directly as current rows.

Timing is tight. The ads start leaving the 7-day window on Oct 20. Unless an nb9 fit is served by then, they would show only as past listings until Data collection crawls again.

Showing unpriced listings from buildings outside the fit would be a new site feature. Under the feature hold I'd add it to the backlog and build it only if you ask for it.

## "Available now" on the live site

The live site runs the Oct 10 20:09Z build. The build sets each listing's current status, so the site still counts 516 listings as available:

- Chelsea: 148, captured Oct 4
- West Village: 87, captured Oct 4
- Greenwich Village: 44, captured Oct 6
- East Village: 94, captured Oct 10
- Flatiron: 34, captured Oct 10
- Gramercy Park: 34, captured Oct 10
- NoMad: 51, captured Oct 10
- Stuyvesant Town/PCV: 24, captured Oct 10

Above the listings, the coverage note gives the age of the older captures: 10 days for Chelsea and West Village, 8 days for Greenwich Village. It warns that some of those listings may have rented, and it points to the StreetEasy link on each listing.

If I rebuilt the site now, Chelsea, West Village and Greenwich Village would drop to 0 and get the "no current capture yet" note. The site would then list 237 available listings, all from the Oct 10 captures, and those leave the window around Oct 17.

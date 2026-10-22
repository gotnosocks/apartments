# Brooklyn ads on Manhattan buildings (2026-10-14)

Read-only investigation. Nothing in the data or repo was changed.

## How it happens

A Brooklyn agent types an address such as "39 East 21st Street" or "509 8th Avenue". Brooklyn has its own East 21st Street (Flatbush), East 17th/18th/19th Streets, 7th and 8th Avenues (Park Slope) and Lexington Avenue (Bed-Stuy). StreetEasy matched those ads to the Manhattan building with that address, or to one whose address range covers it ("316 7th Avenue" went to 300 7th Ave; "100 East 21st Street" went to 257 Park Ave South on the corner), and published them as that building's units.

On every stored page, StreetEasy's own data names the Manhattan building: the page's building link and the listing's URL point to it, the address field says New York with a Manhattan zip (10001 to 10019), and the only coordinates on the page are the building's. Our parser (`src/apartments/granular_parse.py`, `parse_listing`) takes the building from that link, so it inherits StreetEasy's mistake. Nothing in our pipeline joins listings to buildings by address text.

All 28 entered the crawl from the rental inventory on the Manhattan building's StreetEasy page (25 by the inventory unit probe, 3 by inventory or unit membership). None came from search results.

Only the ad text gives them away, and the agents are often Brooklyn firms (Boerum Hill Realty, Brooklyn Blocks, Rapid Realty Cobble Hill).

## The 28 quarantined in v16

URL for each: https://streeteasy.com/rental/ID. Ask is the row's first ask.

| Listing | Our building / unit | StreetEasy's address | Date | Ask | Beds/baths | Agent | Ad text placing it in Brooklyn |
|---|---|---|---|---|---|---|---|
| 2037198 | 300 7th Ave 2C | 316 7th Ave, 10001 | 2017-03 | $2,150 | 1/1 | Boerum Hill Realty | "Close to the F and G subways and only 2 blocks to Prospect Park" |
| 2604683 | 355 7th Ave 3A | 357 7th Ave, 10001 | 2018-12 | $3,200 | 3/1 | ZealEstate | "PRIME PARK SLOPE" |
| 2126824 | 257 Park Ave S 117 | 100 E 21st St, 10010 | 2017-06 | $1,695 | 1/1 | Joel Scharf | "RIGHT NEAR PROSPECT PARK! RIGHT NEAR B and Q TRAINS" |
| 2346231 | The Century Building 216 | 35 E 17th St, 10003 | 2018-03 | $2,390 | 2/1 | Smart NY Realty | "Across from prospect park 2 min walk to Q B trains" |
| 2375574 | 220 E 18th St 25 | 220 E 18th St, 10003 | 2018-04 | $1,350 | studio | Lucrum Group | "Walk to Beverly Road train stop, Cortelyou Road dining and Church Avenue shopping" |
| 2394172 | The Everett Building D3 | 39 E 17th St, 10003 | 2018-05 | $1,800 | 1/1 | Zuz Realty | "steps away from Prospect Park" |
| 2393472 | The Everett Building 3F | 39 E 17th St, 10003 | 2018-05 | $1,800 | 1/1 | Zuz Realty | same ad |
| 2393567 | The Everett Building 3G | 39 E 17th St, 10003 | 2018-05 | $1,800 | 1/1 | Zuz Realty | same ad |
| 2394171 | The Everett Building C3 | 39 E 17th St, 10003 | 2018-05 | $1,800 | 1/1 | Zuz Realty | same ad |
| 2425196 | 63 W 17th St 1DD | "598 6th", 10011 | 2018-06 | $2,750 | 2/1.5 | Realty Nerd | "Gorgeous North Slope 2 bedrooms ... near Prospect park" |
| 2609340 | The Century Building 217 | 33 E 17th St, 10003 | 2018-12 | $1,550 | 1/1 | Brooklyn Blocks | "steps away from Prospect Park and the B/Q subway" |
| 2597994 | 31 E 21st St 6K | 31 E 21st St, 10010 | 2018-12 | $2,012 | 2/1 | Uptown Flats | "Two Blocks from Prospect Park" |
| 3038013 | 37 E 21st St 2D | 39 E 21st St, 10010 | 2020-05 | $2,400 | 1/1 | Keyo | "The Park 21 ... a few blocks from Prospect Park" |
| 3234103 | 37 E 21st St 2B | 39 E 21st St, 10010 | 2020-09 | $1,690 | | Compass | "a refreshingly modern and sleek take on Brooklyn living" |
| 3234140 | 37 E 21st St 5C | 39 E 21st St, 10010 | 2020-09 | $2,450 | | Compass | same ad |
| 3252411 | 37 E 21st St 2B2 | 39 E 21st St, 10010 | 2020-10 | $1,690 | | Compass | same ad |
| 3296867 | 224 Park Ave S A1 | 50 E 19th St, 10003 | 2020-11 | $1,700 | 1/1 | Citified | "2 blocks from Q/B Trains 3 blocks from Prospect Park" |
| 3549752 | 116 E 19th St 3B | 116 E 19th St, 10003 | 2021-06 | $1,825 | 2/1 | ATM Realty | "2 bedroom just minutes from Prospect Park" |
| 4068799 | 205 E 17th St 5B | 205 E 17th St, 10003 | 2023-03 | $1,850 | 1/1 | Queens Apartments Realty | "around the corner from the B,Q on Beverly Road, minutes to Prospect Park and Cortelyou" |
| 4453275 | 260 Park Ave S 3B | 56 E 21st St, 10010 | 2024-06 | $2,799 | 1/1 | ERNY | "Brand new luxury building in the heart of PLG" |
| 4720232 | 149 E 18th St 3 | 149 E 18th St, 10003 | 2025-04 | $2,650 | 2/1 | Arche Nest | "Steps from Prospect Park, Parade Grounds, and B/Q trains" |
| 3409639 | 88 Lexington Ave 203 | 80 Lexington Ave, 10016 | 2021-02 | $3,650 | 3/2 | AYM NYC | "3 BEDROOM NEAR FORT GREENE PARK" |
| 4213089 | 721 E 5th St 2C | 723 E 5th St, 10009 | 2023-08 | $2,650 | 2/1 | Outpost | "2 BR PRIME KENSINGTON ... F/B Train" |
| 1486768 | 519 8th Ave 6 | 509 8th Ave, 10018 | 2015-03 | $3,900 | 2/1 | Farran | "Park Slope on 3rd Street. You are zoned for PS321" |
| 1857324 | 799 8th Ave R3 | 805 8th Ave, 10019 | 2016-08 | $3,000 | 2/1 | Rapid Realty Cobble Hill | "in Park Slope, block away from the Prospect Park" |
| 2374647 | 519 8th Ave 3L | 509 8th Ave, 10018 | 2018-04 | $2,600 | 2/1 | (none) | "Prime Park Slope, just one block to Prospect Park" |
| 3049755 | 799 8th Ave 3F | 809 8th Ave, 10019 | 2020-05 | $3,200 | 2/1 | Ideal Properties | "heart of Park Slope. The F,G at 7th Avenue" |
| 3086352 | 519 8th Ave 2 | 515 Eighth Ave, 10018 | 2020-06 | $5,100 | 4/3 | Metropolitan Realty | "School District 15 ... HEART OF PARK SLOPE" |

## Likely misses (a wider text screen over all 296,953 NB9 rows)

Adding more Brooklyn places (Williamsburg, Boerum Hill, Cobble Hill, Carroll Gardens, Gowanus, Prospect Heights, Kensington, DUMBO, Brooklyn Heights, "Brooklyn", 112xx zips) hit 119 rows: 69 already quarantined, 50 read by hand, most of them false alarms (Kensington House in Chelsea, Brooklyn Fare, broker offices, "Clinton" meaning Hell's Kitchen). These look like real Brooklyn apartments v16 missed:

| Listing | Our building | Date | Beds | Ad text |
|---|---|---|---|---|
| 3365494 | 35 Irving Place (SE: 43 Irving Pl #A) | 2021-01 | 3 | "massive 3 bedroom 2 bathroom on a gorgeous clinton hill block" |
| 3327648 | 88 Lexington Ave (SE: 80 Lexington Ave #31O) | 2020-12 | 1 | "this is a prime clinton hill location" |
| 4846494 | 807 Washington St | 2025-09 | 1 | "right across from brooklyn botanical gardens" |
| 2625018 | 109 5th Ave | 2019-01 | 1 | "1 bedroom apt. in prime north park slope ... barclay's center trains" |
| 1670083 | 77 E 12th St (SE: 126 4th Ave #4A) | 2015-11 | 2 | "luxury no fee building in north park slope/boerum hill walk to atlantic terminal" |
| 1711189 | 429 W 46th St | 2016-01 | 1 | "luxury true 1br in downtown brooklyn is within 1 block of the 2,3,4,5,B,Q,R,G" |
| 5060078 (unclear) | 229 E 21st St | 2026-06 | 3 | "heart of williamsburg", but lists Union Square's subway lines |

## How big it could be

Zip, borough and coordinates can't catch this: of 383,835 parsed listing captures, all but one carry New York and a Manhattan zip, because StreetEasy replaces the agent's address with the building's. Ad text is the only signal, so ads that never name a Brooklyn place stay invisible, and 812 NB9 rows have no ad text at all. Buildings whose address repeats in Brooklyn (numbered East streets in the teens and twenties, 5th/7th/8th Avenue, Lexington, Irving, Washington, Grove, Bleecker) are where any remainder sits.

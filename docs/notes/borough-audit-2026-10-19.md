# Borough audit of the B0 trimmed rows, 2026-10-19

I checked the rows behind the converged B0 fits (#1154 to #1156) for ads outside Manhattan and
Brooklyn and for ads with no borough. I made no data or code changes. The working files are in
`/data1/apartments/tmp/boro-audit/` (per-building table: `odd_buildings.csv`).

## The data and where borough comes from

The fits read `/data1/apartments/frontier/datasets/b0-1ed2cd98fe208d45-offmarket-dense/rows.parquet`,
1,896,486 rows (one per listing), trimmed to start 2013-12-02. The rows carry StreetEasy's
`neighbourhood` but no borough column. Every row has a neighbourhood, and all 64 names belong to
Manhattan or Brooklyn.

B0.4 (`frontier/src/rentfrontier/b0_4.py`, `sites_of`) gives each building a borough from the first
digit of its BBL in the registry snapshot
`/data1/apartments/external/registry/20261017-2c61ff1-all-lots4/registry.parquet`. A building
with no registry row, or no coordinates or BBL there, gets borough `None`.

| BBL borough | rows | buildings |
|---|---:|---:|
| 1 Manhattan | 1,115,594 | 21,940 |
| 3 Brooklyn | 780,414 | 45,937 |
| 4 Queens | 143 | 24 |
| none (unlocated) | 335 | 76 |

Where the registry has a BBL, its borough agrees with the neighbourhood's borough on every
Manhattan and Brooklyn row.

To test the odd 100 buildings independently, I pulled each one's StreetEasy building record from
the API export (`/data1/apartments/archive/crawls/api/export/buildings/`), read its address,
ZIP, community district and `geoCenter`, and placed the point in the city's 2020 NTA polygons
(NYC Open Data 9nt8-h7nd, all boroughs) with `rentfrontier.nta.inside`.

## Queens: 143 rows, 24 buildings, genuine

All 24 buildings are in Ridgewood, Queens, and every source agrees:

- BBL prefix 4 (block 3442, 3444, 3539, 3410, 3729).
- StreetEasy's address gives city RIDGEWOOD, ZIP 11385, community district 405 (Queens CD 5).
- The slug ends in `-ridgewood`.
- The point falls in the Ridgewood NTA (22 buildings) or the Glendale NTA (2 buildings).

StreetEasy files them under its own "Bushwick" area (one under "East Williamsburg"). Its area
polygon runs past Wyckoff Avenue, the borough line, so the Brooklyn search region
`brooklyn-north-crown-heights` collected them. Our `neighbourhood` field copies that label, so
these rows look like Bushwick everywhere except the BBL.

Most sit on the blocks between Wyckoff Avenue, Grove Street, St Nicholas Avenue and Menahan
Street, within about 100 m of the borough line. The exception is 80-52 and 80-60 57th Street
(7 rows), in Glendale about 1.5 km southeast of Wyckoff Avenue, where StreetEasy's "Bushwick" label
stretches furthest.

Examples:

- 1673 Grove St (34 rows, listings 2925760, 2947286, 2951625), BBL 4034420040, Ridgewood NTA.
- 1693 Grove St (23 rows, listings 1360761, 1456351, 1532336), BBL 4034420030, Ridgewood NTA.
- 424 Menahan St (14 rows, listings 3002909, 3511468, 3559261), BBL 4034420025.
- 80-60 57th St (5 rows, listings 2353799, 2353919, 3758451), BBL 4037290013, Glendale NTA.
- 64 Onderdonk Ave (1 row, listing 2988858), BBL 4034100150, labelled East Williamsburg.

These are correct addresses in Queens, so I propose no correction to them. Ben decided on
2026-10-19 to keep them, in the not-Manhattan zone of a two-zone location term.

## No borough: 335 rows, 76 buildings, a registry coverage gap

None of the 76 buildings appears in the registry snapshot or in any earlier registry snapshot
under `/data1/apartments/external/registry/`. The registry's rows came from two building lists
written on 2026-10-15 (`/data1/apartments/frontier/datasets/api-buildings-20261015/`,
manhattan.csv and brooklyn.csv) plus the Midtown West additions of 10-16, and none of the 76
building slugs is in those lists. Their StreetEasy building records came in from building-crawl
runs 2 to 5 on 10-15 (69 buildings) and runs 8 to 15 on 10-16 and 10-17 (7 buildings), so it
looks like the lists were cut before these records arrived. The pipeline holds 70,145 buildings
against the registry's 69,274, so about 870 buildings in all lack a registry row; 76 of them have
rows in the trimmed data.

The ads themselves look sound. Every one of the 76 buildings has a StreetEasy record with
a street address, ZIP and coordinates, the slug matches the ad's page URL, and the point lands
in an NTA of the borough its neighbourhood names:

- 312 rows (51 buildings) in Manhattan, 277 of them in West Chelsea.
- 23 rows (25 buildings) in Brooklyn.

The rows span 2013 to 2026, so the gap cuts into old ads as well as new ones. The largest
buildings:

- 401 W 25th St, slug `401-west-25-street-manhattan` (161 rows; listings 1219373, 1220361,
  1236544): ZIP 10001, point in the Chelsea-Hudson Yards NTA.
- 205 10th Ave (39 rows; listings 1211954, 1214731, 1327924): ZIP 10011, CD 104.
- 421 W 24th St (22 rows; listings 3081929, 3142336, 3258303): ZIP 10011, CD 104.
- 508 W 24th St (11 rows; listings 1479364, 1620282, 2164023).
- 139 Berkeley Pl, Brooklyn (2 rows; listings 1553803, 1757035): ZIP 11217, CD 306, Park Slope NTA.

Proposed correction: geocode the missing buildings through `rentfrontier.registry` in the
usual way, from the slug address checked against the StreetEasy coordinates, and cut a new
registry snapshot. The independent backing is the StreetEasy building record (address, ZIP,
community district, coordinates) together with the NTA point test, without reference to ad
text. Running the full
pipeline building list, rather than these 76 alone, also covers the other 800 or so missing
buildings.

## How a two-zone location term would assign these rows

No two-zone code exists yet on master or the `b0-5` branch. B0.4 shows how the current
pieces behave:

1. Zone comes from the registry BBL digit (`sites_of`). B0.4 gives Queens and unlocated rows
   their own intercepts (`boro:queens`, `boro:unlocated`) and puts them on no surface (they map
   to the site index past the last surface).
2. If a two-zone design tests `boro == "1"` for Manhattan and treats everything else as not
   Manhattan, then:
    - the 143 Queens rows join the not-Manhattan zone and, since they have coordinates, its
      surface. They lie inside the east-west span the Brooklyn buildings already cover (3 Crosby
      Ave in Cypress Hills reaches -73.896), so the surface's box barely changes.
    - the 335 unlocated rows have no coordinates, so they take the not-Manhattan intercept with
      no surface. 312 of them are Manhattan ads, and they would be priced as outer-borough ads.
3. If the zone came from `neighbourhood` instead, the unlocated rows would land in the right zone,
   but the Queens rows would count as Brooklyn (StreetEasy calls them Bushwick), and the
   unlocated rows would still have no position on a surface.

Before a two-zone fit, I recommend:

- Fill the registry gap first (above), so every row has a BBL and a point. After that the BBL
  digit and the point-in-polygon borough agree on every row I checked.
- Keep the Queens rows in the not-Manhattan zone (Ben, 2026-10-19). The zone test on the BBL
  digit, `boro == "1"` for Manhattan, already puts them there, and the surface takes them as a
  small eastern fringe of Bushwick.
- Have the design refuse, or at least count and report, any row without coordinates, rather
  than folding it into a zone's intercept.

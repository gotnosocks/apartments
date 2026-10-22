# Outside rent data: what can be downloaded today

*Checked 2026-10-15 by web search and by reading each source's own page. Nothing was downloaded and no budget was spent. The cloud machine that runs project threads is blocked from city and Census sites, so the downloads themselves have to run on thelio. They are all free.*

## Summary

| Source | What it gives | Where | Fit for our buildings | Verdict |
|---|---|---|---|---|
| **Department of Finance comparable rental income** | For about 31,600 condo/co-op valuations (2012–2018), the actual rental buildings DOF used as comparables, each with BBL, address, units, year built, gross sq ft, **gross income per sq ft**, expenses and market value | NYC Open Data `9ck6-2jew`, CSV | Building-level, keyed by BBL, so it joins straight onto our buildings | **Best independent check. Download first.** |
| **Housing and Vacancy Survey 2021 and 2023** | About 15,600 sampled homes each, with the rent actually paid, rent-stabilised or not, bedrooms, rooms, year moved in, condition problems, survey weights | nyc.gov/assets/hpd/data/*_puf_23.csv and *_puf_21.csv | **Borough only.** No finer location on the public files. Contract rent is capped at $7,500 (2023) and $6,330 (2021) | Useful only for a Manhattan-wide check of the gap between asks and rents paid, by bedroom count and stabilised status |
| **Housing and Vacancy Survey, 2017 and earlier** | Same survey, and I believe older public files carried sub-borough areas (about 10 in Manhattan, e.g. Chelsea/Clinton/Midtown) | Census and HPD archives | Area-level, older | Not confirmed; check the 2017 codebook on thelio |
| **Rent-stabilised building list (2024)** | Addresses of buildings with at least one stabilised unit | Rent Guidelines Board, Manhattan PDF | Presence only, no unit counts, PDF that needs parsing | Usable as a building flag after parsing |
| **Stabilised unit counts from tax bills** | Stabilised unit counts per building (BBL) for about 2007–2017, scraped from DOF tax bills by volunteers | nyc-db (antievictionmappingproject) and related projects | Building-level, older | Worth a look; not checked in detail |
| **DOB certificates of occupancy / DCP Housing Database** | Legal unit counts and new-construction and conversion records per building | NYC Open Data | Building-level | Available; supports unit-count and conversion checks |
| **2017 city LiDAR** | 22.8 billion classified points, 2,500 ft tiles, free | NOAA bucket `noaa-nos-coastal-lidar-pds`, LAZ, dataset 9306 | Per building and window; misses anything built after mid-2017 (most of Hudson Yards) | Available. The light-and-view work is a larger project, not a quick check |

## What I'd do next (all free, on thelio)

1. **Download the Finance comparable-income file** (one CSV) and match its rental buildings to ours by BBL. Then compare, building by building, our model's median rent per sq ft for 2012–2018 asks with the income per sq ft the owners reported. Expect a gap: reported income includes stabilised and long-tenured units and vacancy, and asks don't. So the test is whether buildings rank in the same order and whether the gap follows stabilised share, not whether the levels match. That gives an outside answer to "is the building part of the model right?"
2. **Run the market-reaction test** on data we already hold: do ads priced above the model's median sit longer and get cut toward it? No outside data needed.
3. **Use the 2023 survey for one Manhattan-wide number:** how far asks sit above what recent movers actually pay, by bedroom count. This is a calibration fact, not a building-level check.
4. **Leave LiDAR** until the photo and floor-plan quality work is under way. It's free and available, but turning it into light and views per window is real work.

## Sources

- [DOF Condominium Comparable Rental Income (data.gov)](https://catalog.data.gov/dataset/dof-condominium-comparable-rental-income-in-nyc); columns from `data.cityofnewyork.us/api/views/9ck6-2jew/columns.json`
- [HPD research page with HVS public use files](https://www.nyc.gov/site/hpd/about/research.page); [2023 HVS user guide](https://www.nyc.gov/assets/hpd/downloads/pdfs/about/2023-nychvs-puf-user-guide-codebook.pdf); [2021 HVS user guide](https://www.nyc.gov/assets/hpd/downloads/pdfs/about/research/userguidecodebook.pdf)
- [Rent Guidelines Board, rent-stabilised building lists](https://rentguidelinesboard.cityofnewyork.us/resources/rent-stabilized-building-lists/)
- [nyc-db](https://github.com/antievictionmappingproject/nyc-db)
- [DOB Certificate of Occupancy (data.gov)](https://catalog.data.gov/dataset/dob-certificate-of-occupancy)
- [2017 NYC Topobathy Lidar (NOAA InPort 64728)](https://www.fisheries.noaa.gov/inport/item/64728)

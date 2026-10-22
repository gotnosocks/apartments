# Building features: NYC coverage (2026-10-21)

This is a read-only check on thelio against the NYC-only dataset `b0-30b3edae310c2fae-alldata-v36-dense-nyc`. It has 1,896,486 rows and 67,977 buildings: 1,115,906 rows in Manhattan and 780,580 in Brooklyn + Queens, with the borough taken from the BBL. A building counts as known when any of its ads, or its lot, gives a value. Figures are shown as Manhattan / Brooklyn + Queens. The scripts and the full table (`coverage.csv`, `amenities.parquet`) are in `/data1/apartments/tmp/zones-explainer/` on thelio.

## The five features in the building-attributes fit (snapshot 20261020-0a7254f)

| Feature | Source | Rows known % | Buildings known % | Notes |
|---|---|---|---|---|
| Floors | ads, then PLUTO | 99.9 / 99.8 | 99.4 / 99.5 | From the ads alone: rows 96.7 / 97.7 |
| Elevator | ads, then PLUTO class | 99.7 / 98.7 | 95.4 / 95.2 | From the ads alone: rows 95.5 / 61.4, buildings 78.3 / 26.0, so outside Manhattan this is mostly the coarse PLUTO class |
| Doorman stated | ads | 54.2 / 49.4 | 26.7 / 19.5 | "None stated" means the ads don't say, not that there is no doorman |
| Year built (era) | PLUTO | 99.6 / 99.5 | 98.8 / 99.2 | |
| Tenure | PLUTO class | 99.8+ | 99.8+ | |

## Other fields already held

**Coded ad fields**, per building from any of its ads. These are in the pipeline rows but not in a snapshot.

| Field | Rows % | Buildings % | Notes |
|---|---|---|---|
| laundry_type | 89.8 / 85.6 | 75.0 / 62.5 | |
| pet_policy | 88.1 / 85.3 | 66.4 / 62.4 | Only source for pets |
| hvac_type | 63.9 / 74.3 | 42.9 / 44.6 | Nearly all values are central_ac |

**StreetEasy amenity codes**, from each listing's latest raw record. These would need building into a snapshot. Between 97% and 98% of buildings list at least one code. A code only marks presence, so a missing code means "not stated".

Share of rows in buildings that list each code:

| Code | Rows % |
|---|---|
| live-in super | 86 / 65 |
| laundry | 82 / 78 |
| shared outdoor | 74 / 81 |
| doorman | 71 / 69 |
| storage | 70 / 60 |
| elevator | 65 / 41 |
| package room | 59 / 52 |
| roof deck | 58 / 68 |
| bike room | 50 / 62 |
| gym | 47 / 36 |
| concierge | 47 / 24 |
| parking | 45 / 37 |
| pool | 22 / 11 |

By building the shares are much lower: gym 18 / 7.5, roof deck 33 / 30.

**PLUTO** (20261017 all-lots4):
- Rows 97% to 100% for yearbuilt, numfloors, unitsres, unitstotal, lotarea, bldgarea, resarea, builtfar, residfar, bldgclass, landuse, zonedist1 and lotfront.
- bldgfront and bldgdepth: rows 92 / 95.
- The following are flags, so every lot has a value:
  - comarea above 0: rows 71 / 35;
  - yearalter1 set: rows 49 / 39;
  - histdist: rows 16.8 / 10.1;
  - landmark: rows 2.5 / 0.5.

**Footprints** (20261016):
- height_roof: rows 97.5 / 99.3.
- construction_year: rows 96.6 / 98.3.
- Both join through the registry BIN, which is real for rows 98.0 / 96.7.

**LPC designations:** rows 19.3 / 10.7 sit on a designated lot. The snapshot holds no Queens lots.

**Manhattan only.** These snapshots hold Manhattan BBLs only:
- rent-stabilized unit counts from tax bills, 2007 to 2024 (74.5% of Manhattan rows have stabilized units);
- HPD violations (30%);
- DOB A1, A2 and NB jobs (9.6%);
- HousingDB (7%).

**Location layers.** These reach every row, since every row has a point: subway with lines and ADA, GTFS and MTA-GTFS, PATH, parks and riverparks, trees, 311 noise, crime, storefronts, LODES jobs, NTA and places.

## Suspect values

1. **PLUTO floors on shared lots (the 8 Spruce pattern).**
   - Where the ads and PLUTO both give floors, they differ by 3 or more for 725 of 65,241 buildings.
   - PLUTO is the only floors source for 1,898 buildings, and 1,481 of those share a lot.
   - About 2% of buildings carry a doubtful floor count.
2. **Shared lots.** 4,664 buildings share a BBL, so every lot-level field is the same across them. Rows on such lots: 11% / 9%.
3. **Elevator outside Manhattan** comes mostly from the PLUTO class.
4. **Presence-only ad codes.** Reading a missing code as "no" would bias the doorman, elevator and amenity terms.

## Could be fetched cheaply (NYC Open Data)

- The Manhattan-only feeds for Brooklyn and Queens: rent-stabilization tax-bill counts, HPD registrations and violations, DOB and DOB NOW jobs, HousingDB.
- Certificates of occupancy (not held for any borough).
- DOF assessed market value per lot.
- ACRIS sales and condo unit records.
- J-51 and 421a exemption rolls.
- DOB elevator device records, as an independent elevator source.

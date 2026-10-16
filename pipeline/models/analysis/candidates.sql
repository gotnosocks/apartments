MODEL (
    name analysis.candidates,
    kind FULL,
    grain listing_id,
    audits (
        unique_values(columns := (listing_id)),
        not_null(
            columns := (listing_id, unit_id, building, price_at, period, asking_rent, bedrooms, fate)
        )
    ),
    description 'Each ad the current chain accepts before its unit-month check, with its fit-ready values and its fate in that check.'
);

-- The candidates are the ads with a unit and with no reason in ads.exclusions. The chain keeps a
-- row for each unit and month of first day, in two steps:
--   1. `historical_dataset` drops every ad of a unit-month whose ads give two bedroom counts or
--      two bathroom counts. Their fate is `conflicting_layout_same_unit_month`.
--   2. `rentfrontier.cohort` keeps the ad with the latest first day in each other unit-month,
--      and of those the one with the greatest ad ID, compared as text. The other ads' fate is
--      `superseded_in_unit_month`.
-- The chain checks a unit-month within a building slice of a region's dataset, while this model
-- checks it over all regions.
--
-- The values follow the chain's analysis rows:
--   - `price_at` is midnight UTC of the first day, and `period` its month.
--   - `square_feet` outside 150 to 6,000 counts as unknown.
--   - `listed_floor` is the ad's advertised floor, when it has one. Otherwise it's the floor its
--     unit labels read in ads.reported. The chain refuses a label floor above the building's
--     floor count, or of 10 or more when the building has no count. `floor_status` gives the
--     reason, and `label_derived_floor` repeats a floor that came from the labels.
--   - `neighbourhood` is the area of the ad's building in buildings.details.
--   - `regions` lists the export regions of the ad's answers.
WITH candidates AS (
    SELECT e.listing_id, e.first_day, e.rent, i.unit_id, i.page, i.building, i.building_id,
        t.bedrooms, t.bathrooms, t.square_feet, t.advertised_floor, t.physical_floor,
        t.floors_above_ground, t.elevator, t.laundry_type, t.doorman_type, t.hvac_type,
        t.pet_policy, t.view_exposures, t.window_exposures,
        r.label_floor, r.full_baths, r.half_baths, b.floor_count, b.area,
        date_trunc('month', e.first_day)::DATE AS period
    FROM ads.exclusions e
    JOIN ads.identity i USING (listing_id)
    JOIN ads.attributes t USING (listing_id)
    JOIN ads.reported r USING (listing_id)
    LEFT JOIN buildings.details b ON b.building_id = i.building_id
    WHERE e.reasons = [] AND i.reasons = []
),
regions AS (
    SELECT listing_id::VARCHAR AS listing_id, list_sort(list(DISTINCT region)) AS regions
    FROM raw.ads
    GROUP BY listing_id
),
checked AS (
    SELECT *,
        CASE
            WHEN advertised_floor IS NOT NULL THEN 'explicit_source_floor'
            WHEN label_floor IS NULL THEN 'unresolved_or_conflicting_capture_labels'
            WHEN label_floor > floor_count THEN 'above_captured_building_floor_count'
            WHEN floor_count IS NULL AND label_floor >= 10 THEN 'two_digit_label_without_building_count'
            ELSE 'label_proxy'
        END AS floor_status,
        CASE
            WHEN min(bedrooms) OVER unit_month <> max(bedrooms) OVER unit_month
                OR min(bathrooms) OVER unit_month <> max(bathrooms) OVER unit_month
                THEN 'conflicting_layout_same_unit_month'
            WHEN row_number() OVER (
                PARTITION BY unit_id, period ORDER BY first_day DESC, listing_id DESC
            ) > 1
                THEN 'superseded_in_unit_month'
            ELSE 'kept'
        END AS fate
    FROM candidates
    WINDOW unit_month AS (PARTITION BY unit_id, period)
)
SELECT c.listing_id, c.unit_id, c.page, c.building, c.building_id, g.regions,
    c.first_day::TIMESTAMP AT TIME ZONE 'UTC' AS price_at, c.period,
    c.rent AS asking_rent, c.bedrooms, c.bathrooms, c.full_baths, c.half_baths,
    CASE WHEN c.square_feet BETWEEN 150 AND 6000 THEN c.square_feet END AS square_feet,
    CASE
        WHEN c.floor_status = 'explicit_source_floor' THEN c.advertised_floor
        WHEN c.floor_status = 'label_proxy' THEN c.label_floor
    END AS listed_floor,
    CASE WHEN c.floor_status = 'label_proxy' THEN c.label_floor END AS label_derived_floor,
    c.floor_status, c.floor_count AS building_floor_count,
    c.advertised_floor, c.physical_floor, c.floors_above_ground, c.elevator, c.laundry_type,
    c.doorman_type, c.hvac_type, c.pet_policy, c.view_exposures, c.window_exposures,
    c.area AS neighbourhood, c.fate
FROM checked c
JOIN regions g USING (listing_id)

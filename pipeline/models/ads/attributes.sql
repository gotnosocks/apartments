MODEL (
    name ads.attributes,
    kind FULL,
    grain listing_id,
    audits (unique_values(columns := (listing_id)), not_null(columns := (listing_id, records, conflicts))),
    description 'Each ad''s attributes and rental flags, merged over its records as the current chain merges its captures.'
);

-- An ad's records are the distinct records of its answers. The current parser fails on a
-- record with another ad's `id` or without propertyDetails and gives it a capture without
-- values, so such a record takes no part here. For each attribute, this model compares the
-- records' values as canonical JSON and ignores unknowns, as `project_advertisement` does: one
-- value stands, two or more give an unknown, and the attribute's name goes into `conflicts`.
-- A rental flag is true when any record sets it, false when the records give only false, and
-- unknown when they give nothing. `records` holds the number of merged records. When all of an
-- ad's records fail to parse, the ad gets no row.
WITH projected AS (
    SELECT DISTINCT a.listing_id::VARCHAR AS listing_id, r.* EXCLUDE (id, parsed)
    FROM ads.answers a
    JOIN ads.record_attributes r USING (record_sha256)
    WHERE a.outcome = 'record' AND r.parsed AND r.id = a.listing_id::VARCHAR
),
merged AS (
    SELECT listing_id, count(*) AS records,
        count(DISTINCT bedrooms) AS n_bedrooms, min(bedrooms) AS bedrooms,
        count(DISTINCT bathrooms) AS n_bathrooms, min(bathrooms) AS bathrooms,
        count(DISTINCT square_feet) AS n_square_feet, min(square_feet) AS square_feet,
        count(DISTINCT advertised_floor) AS n_advertised_floor, min(advertised_floor) AS advertised_floor,
        count(DISTINCT physical_floor) AS n_physical_floor, min(physical_floor) AS physical_floor,
        count(DISTINCT floors_above_ground) AS n_floors_above_ground, min(floors_above_ground) AS floors_above_ground,
        count(DISTINCT elevator) AS n_elevator, min(elevator) AS elevator,
        count(DISTINCT laundry_type) AS n_laundry_type, min(laundry_type) AS laundry_type,
        count(DISTINCT doorman_type) AS n_doorman_type, min(doorman_type) AS doorman_type,
        count(DISTINCT hvac_type) AS n_hvac_type, min(hvac_type) AS hvac_type,
        count(DISTINCT pet_policy) AS n_pet_policy, min(pet_policy) AS pet_policy,
        count(DISTINCT view_exposures) AS n_view_exposures, min(view_exposures) AS view_exposures,
        count(DISTINCT window_exposures) AS n_window_exposures, min(window_exposures) AS window_exposures,
        bool_or(furnished::BOOLEAN) AS furnished,
        bool_or(short_term::BOOLEAN) AS short_term,
        bool_or(concession::BOOLEAN) AS concession
    FROM projected
    GROUP BY listing_id
)
SELECT listing_id, records,
    CASE WHEN n_bedrooms = 1 THEN bedrooms::DOUBLE END AS bedrooms,
    CASE WHEN n_bathrooms = 1 THEN bathrooms::DOUBLE END AS bathrooms,
    CASE WHEN n_square_feet = 1 THEN square_feet::DOUBLE END AS square_feet,
    CASE WHEN n_advertised_floor = 1 THEN advertised_floor::DOUBLE END AS advertised_floor,
    CASE WHEN n_physical_floor = 1 THEN physical_floor::DOUBLE END AS physical_floor,
    CASE WHEN n_floors_above_ground = 1 THEN floors_above_ground::DOUBLE END AS floors_above_ground,
    CASE WHEN n_elevator = 1 THEN elevator::BOOLEAN END AS elevator,
    CASE WHEN n_laundry_type = 1 THEN laundry_type::JSON ->> '$' END AS laundry_type,
    CASE WHEN n_doorman_type = 1 THEN doorman_type::JSON ->> '$' END AS doorman_type,
    CASE WHEN n_hvac_type = 1 THEN hvac_type::JSON ->> '$' END AS hvac_type,
    CASE WHEN n_pet_policy = 1 THEN pet_policy::JSON ->> '$' END AS pet_policy,
    CASE WHEN n_view_exposures = 1 THEN view_exposures::JSON END AS view_exposures,
    CASE WHEN n_window_exposures = 1 THEN window_exposures::JSON END AS window_exposures,
    furnished, short_term, concession,
    list_filter(
        ['bedrooms', 'bathrooms', 'square_feet', 'advertised_floor', 'physical_floor',
         'floors_above_ground', 'elevator', 'laundry_type', 'doorman_type', 'hvac_type',
         'pet_policy', 'view_exposures', 'window_exposures'],
        (key, i) -> [n_bedrooms, n_bathrooms, n_square_feet, n_advertised_floor, n_physical_floor,
                     n_floors_above_ground, n_elevator, n_laundry_type, n_doorman_type, n_hvac_type,
                     n_pet_policy, n_view_exposures, n_window_exposures][i] > 1
    ) AS conflicts
FROM merged

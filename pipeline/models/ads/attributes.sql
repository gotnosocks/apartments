MODEL (
    name ads.attributes,
    kind FULL,
    grain listing_id,
    audits (unique_values(columns := (listing_id)), not_null(columns := (listing_id, records, conflicts))),
    description 'Each ad''s attributes and rental flags, merged over its records as the current chain merges its captures, the attributes only up to its last ACTIVE record.'
);

-- An ad's attributes come from the distinct records of its answers fetched up to its last answer
-- with status ACTIVE, or of all its answers when it has no ACTIVE answer. Once an ad is rented or
-- delisted, StreetEasy strips or cuts its description, and a later record can give other values.
-- The fit's target is the latest ask, so the attributes describe the ad as it stood when it last
-- asked. The rental flags come from all of the ad's records. They describe the terms behind the
-- ask, and a record fetched after the ad closed can state them for the first time. The current
-- parser fails on a record with another ad's `id` or without propertyDetails and gives it a
-- capture without values, so such a record takes no part here.
-- For each attribute, this model compares the records' values as canonical JSON and ignores
-- unknowns, as `project_advertisement` does: one value stands, two or more give an unknown, and
-- the attribute's name goes into `conflicts`. The records of an ad give two or more values
-- exactly when their smallest and largest values differ, so this model takes each attribute's
-- minimum and maximum.
-- A rental flag is true when any record sets it, false when the records give only false, and
-- unknown when they give nothing. `records` holds the number of records merged for the
-- attributes. When all of those records fail to parse, the ad gets no row.
WITH answers AS (
    SELECT listing_id::VARCHAR AS listing_id, record_sha256, fetched,
        max(fetched) FILTER (WHERE status = 'ACTIVE') OVER (PARTITION BY listing_id) AS last_active
    FROM ads.answers
    WHERE outcome = 'record'
),
records AS (
    SELECT listing_id, record_sha256,
        bool_or(last_active IS NULL OR fetched <= last_active) AS until_active
    FROM answers
    GROUP BY listing_id, record_sha256
),
projected AS (
    SELECT a.listing_id, a.until_active, r.* EXCLUDE (record_sha256, id, parsed)
    FROM records a
    JOIN ads.record_attributes r USING (record_sha256)
    WHERE r.parsed AND r.id = a.listing_id
),
flags AS (
    SELECT listing_id,
        bool_or(furnished::BOOLEAN) AS furnished,
        bool_or(short_term::BOOLEAN) AS short_term,
        bool_or(concession::BOOLEAN) AS concession
    FROM projected
    GROUP BY listing_id
),
merged AS (
    SELECT listing_id, count(*) AS records,
        min(bedrooms) AS bedrooms, max(bedrooms) AS bedrooms_max,
        min(bathrooms) AS bathrooms, max(bathrooms) AS bathrooms_max,
        min(square_feet) AS square_feet, max(square_feet) AS square_feet_max,
        min(advertised_floor) AS advertised_floor, max(advertised_floor) AS advertised_floor_max,
        min(physical_floor) AS physical_floor, max(physical_floor) AS physical_floor_max,
        min(floors_above_ground) AS floors_above_ground, max(floors_above_ground) AS floors_above_ground_max,
        min(elevator) AS elevator, max(elevator) AS elevator_max,
        min(laundry_type) AS laundry_type, max(laundry_type) AS laundry_type_max,
        min(doorman_type) AS doorman_type, max(doorman_type) AS doorman_type_max,
        min(hvac_type) AS hvac_type, max(hvac_type) AS hvac_type_max,
        min(pet_policy) AS pet_policy, max(pet_policy) AS pet_policy_max,
        min(view_exposures) AS view_exposures, max(view_exposures) AS view_exposures_max,
        min(window_exposures) AS window_exposures, max(window_exposures) AS window_exposures_max
    FROM projected
    WHERE until_active
    GROUP BY listing_id
)
SELECT listing_id, records,
    CASE WHEN bedrooms = bedrooms_max THEN bedrooms::DOUBLE END AS bedrooms,
    CASE WHEN bathrooms = bathrooms_max THEN bathrooms::DOUBLE END AS bathrooms,
    CASE WHEN square_feet = square_feet_max THEN square_feet::DOUBLE END AS square_feet,
    CASE WHEN advertised_floor = advertised_floor_max THEN advertised_floor::DOUBLE END AS advertised_floor,
    CASE WHEN physical_floor = physical_floor_max THEN physical_floor::DOUBLE END AS physical_floor,
    CASE WHEN floors_above_ground = floors_above_ground_max THEN floors_above_ground::DOUBLE END AS floors_above_ground,
    CASE WHEN elevator = elevator_max THEN elevator::BOOLEAN END AS elevator,
    CASE WHEN laundry_type = laundry_type_max THEN laundry_type::JSON ->> '$' END AS laundry_type,
    CASE WHEN doorman_type = doorman_type_max THEN doorman_type::JSON ->> '$' END AS doorman_type,
    CASE WHEN hvac_type = hvac_type_max THEN hvac_type::JSON ->> '$' END AS hvac_type,
    CASE WHEN pet_policy = pet_policy_max THEN pet_policy::JSON ->> '$' END AS pet_policy,
    CASE WHEN view_exposures = view_exposures_max THEN view_exposures::JSON END AS view_exposures,
    CASE WHEN window_exposures = window_exposures_max THEN window_exposures::JSON END AS window_exposures,
    furnished, short_term, concession,
    list_filter(
        ['bedrooms', 'bathrooms', 'square_feet', 'advertised_floor', 'physical_floor',
            'floors_above_ground', 'elevator', 'laundry_type', 'doorman_type', 'hvac_type',
            'pet_policy', 'view_exposures', 'window_exposures'],
        (key, i) -> coalesce(list_extract([
            bedrooms <> bedrooms_max,
            bathrooms <> bathrooms_max,
            square_feet <> square_feet_max,
            advertised_floor <> advertised_floor_max,
            physical_floor <> physical_floor_max,
            floors_above_ground <> floors_above_ground_max,
            elevator <> elevator_max,
            laundry_type <> laundry_type_max,
            doorman_type <> doorman_type_max,
            hvac_type <> hvac_type_max,
            pet_policy <> pet_policy_max,
            view_exposures <> view_exposures_max,
            window_exposures <> window_exposures_max
        ], i), false)
    ) AS conflicts
FROM merged
JOIN flags USING (listing_id)

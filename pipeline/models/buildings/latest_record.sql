MODEL (
    name buildings.latest_record,
    kind FULL,
    grain building_id,
    audits (unique_values(columns := (building_id)), not_null(columns := (building_id, response_id))),
    description 'Each building with a record: the slug, address, map point and city facts of its latest record.'
);

-- The model takes each building's latest record, by fetch time and then response ID, as
-- `buildings.details` does. It picks the response IDs first and then reads only their records,
-- so DuckDB holds about 70,000 records at a time rather than all of them.
--
-- `slug` is the building's name in StreetEasy's links, such as `1-water-street-new_york`, and
-- the lot registries under /data1/apartments/external/registry list buildings by it. `street`
-- holds the house number and the street, as in `129 West 89th Street`, and the map point is
-- the record's `geoCenter`. StreetEasy shows four city facts on the building's page, mostly
-- copied from city records for the lot it links: the building class, the year built, the floor
-- count and the count of apartments. `buildings.lots` compares them with MapPLUTO's record of
-- each candidate lot. A year or floor count of zero, and an empty class, read as missing. A
-- value of another JSON type, such as a floor count of `true`, reads as missing too.
WITH ids AS (
    SELECT building_id, arg_max(response_id, (fetched, response_id)) AS response_id
    FROM raw.buildings
    WHERE outcome = 'record'
    GROUP BY building_id
), latest AS (
    SELECT building_id, response_id, record
    FROM raw.buildings JOIN ids USING (building_id, response_id)
    WHERE outcome = 'record'
)
SELECT building_id, response_id,
    record ->> '$.slug' AS slug,
    record ->> '$.address.street' AS street,
    record ->> '$.address.zipCode' AS zip,
    record ->> '$.address.city' AS city,
    record ->> '$.nyc.communityDistrict' AS community_district,
    CASE WHEN json_type(record, '$.geoCenter.latitude') IN ('UBIGINT', 'BIGINT', 'DOUBLE')
        THEN (record ->> '$.geoCenter.latitude')::DOUBLE END AS latitude,
    CASE WHEN json_type(record, '$.geoCenter.longitude') IN ('UBIGINT', 'BIGINT', 'DOUBLE')
        THEN (record ->> '$.geoCenter.longitude')::DOUBLE END AS longitude,
    nullif(trim(record ->> '$.nyc.buildingClass'), '') AS building_class,
    CASE WHEN json_type(record, '$.yearBuilt') IN ('UBIGINT', 'BIGINT')
        THEN nullif(try_cast(record ->> '$.yearBuilt' AS INTEGER), 0) END AS year_built,
    CASE WHEN json_type(record, '$.floorCount') IN ('UBIGINT', 'BIGINT', 'DOUBLE')
        THEN nullif((record ->> '$.floorCount')::DOUBLE, 0) END AS floor_count,
    CASE WHEN json_type(record, '$.residentialUnitCount') IN ('UBIGINT', 'BIGINT')
        THEN try_cast(record ->> '$.residentialUnitCount' AS INTEGER) END AS residential_units
FROM latest

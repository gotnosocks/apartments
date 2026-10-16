MODEL (
    name buildings.details,
    kind FULL,
    grain building_id,
    audits (unique_values(columns := (building_id)), not_null(columns := (building_id, records))),
    description 'Each building with a record, with the slug and area of its latest record and its floor count.'
);

-- The slug and the area name come from the building's latest record. The floor count is the
-- smallest positive `floorCount` among its records, rounded down, as `floor_counts` of
-- `rentfrontier.cohort` takes it. The chain also counts a boolean `true` as one floor, since
-- Python's `True` is an int, while this model skips a boolean. No building record of runs 1 to 5
-- gives one. The chain takes the area name most of a building's records give, and it keys both
-- values on the slug rather than the building's ID. The export answers each building once in
-- runs 1 to 5, so the two readings agree there. Answers without a record take no part.
SELECT building_id, count(*) AS records,
    arg_max_null(record ->> '$.slug', (fetched, response_id)) AS slug,
    arg_max_null(record ->> '$.area.name', (fetched, response_id)) AS area,
    min(CASE WHEN json_type(record, '$.floorCount') IN ('UBIGINT', 'BIGINT', 'DOUBLE')
            AND (record ->> '$.floorCount')::DOUBLE > 0
        THEN floor((record ->> '$.floorCount')::DOUBLE)::BIGINT END) AS floor_count
FROM raw.buildings
WHERE outcome = 'record'
GROUP BY building_id

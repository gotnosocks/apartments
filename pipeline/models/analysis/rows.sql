MODEL (
    name analysis.rows,
    kind VIEW,
    grain listing_id,
    description 'The fit-ready rows: a row for each unit and month, from the candidates the unit-month check keeps.'
);

SELECT * EXCLUDE (fate)
FROM analysis.candidates
WHERE fate = 'kept'

MODEL (
    name analysis.kept,
    kind VIEW,
    grain listing_id,
    description 'A row for each unit and month, from the candidates the unit-month check keeps, before the corrections ledger.'
);

SELECT * EXCLUDE (fate)
FROM analysis.candidates
WHERE fate = 'kept'

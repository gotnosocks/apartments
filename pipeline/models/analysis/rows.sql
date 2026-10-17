MODEL (
    name analysis.rows,
    kind VIEW,
    grain listing_id,
    audits (unique_values(columns := (listing_id))),
    description 'The fit-ready rows: the corrected rows less the rows analysis.ask_check lists.'
);

SELECT *
FROM analysis.corrected
WHERE listing_id NOT IN (SELECT listing_id FROM analysis.ask_check)

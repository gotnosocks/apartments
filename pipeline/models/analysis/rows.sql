MODEL (
    name analysis.rows,
    kind VIEW,
    grain listing_id,
    audits (unique_values(columns := (listing_id))),
    description 'The fit-ready rows: the rows of analysis.ledger_rows, each with the label unit of its unit.'
);

-- The last column, `label_unit`, takes the unit analysis.label_units joins the row's unit into,
-- or the row's unit itself. The observations take it as the row's `unit_id`.
SELECT r.*, coalesce(l.label_unit, r.unit_id) AS label_unit
FROM analysis.ledger_rows r
LEFT JOIN analysis.label_units l USING (unit_id)

MODEL (
    name analysis.rows,
    kind VIEW,
    grain listing_id,
    audits (unique_values(columns := (listing_id))),
    description 'The fit-ready rows: the rows of analysis.ledger_rows, each with the label unit of its unit and its piece of that label unit.'
);

-- `label_unit` takes the unit analysis.label_units joins the row's unit into, or the row's unit
-- itself. The last column, `split_unit`, takes the piece analysis.history_splits gives the row,
-- or its label unit. The observations take it as the row's `unit_id`.
SELECT r.*, coalesce(l.label_unit, r.unit_id) AS label_unit,
    coalesce(s.split_unit, l.label_unit, r.unit_id) AS split_unit
FROM analysis.ledger_rows r
LEFT JOIN analysis.label_units l USING (unit_id)
LEFT JOIN analysis.history_splits s USING (listing_id)

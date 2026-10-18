MODEL (
    name analysis.label_months,
    kind FULL,
    grain listing_id,
    audits (
        unique_values(columns := (listing_id)),
        not_null(columns := (listing_id, label_unit, period, fate))
    ),
    description 'Each row of analysis.ledger_rows the unit-month check on label units drops, with its label unit, its month and its fate.'
);

-- analysis.candidates checks each unit-month on the unit pages, as the chain does, and
-- analysis.label_units joins pages into label units afterwards. Two pages of one apartment, such
-- as the pages of two brokers listing it, can then each keep a row in the same month. This model
-- runs the same check again on each row's label unit, after the corrections ledger, so a
-- corrected bedroom count counts in it:
--   1. Every row of a label-month whose rows give two bedroom counts or two bathroom counts
--      drops, with the fate `conflicting_layout_same_label_month`. A bath set of the ledger
--      leaves `bathrooms` as recorded, so only a bedroom set changes this step.
--   2. In each other label-month, the row with the latest first day stays, and of those the one
--      with the greatest ad ID, compared as text. The other rows drop, with the fate
--      `superseded_in_label_month`.
-- The label unit is the one analysis.rows gives the row: the unit analysis.label_units joins
-- the row's unit into, or the unit itself. analysis.history_splits cuts the label units after
-- this check, as the fit's `unit-splits-v4` runs after every other rule.
WITH r AS (
    SELECT r.listing_id, coalesce(l.label_unit, r.unit_id) AS label_unit, r.period, r.price_at,
        r.bedrooms, r.bathrooms
    FROM analysis.ledger_rows r
    LEFT JOIN analysis.label_units l USING (unit_id)
),
checked AS (
    SELECT listing_id, label_unit, period,
        CASE
            WHEN min(bedrooms) OVER label_month <> max(bedrooms) OVER label_month
                OR min(bathrooms) OVER label_month <> max(bathrooms) OVER label_month
                THEN 'conflicting_layout_same_label_month'
            WHEN row_number() OVER (
                PARTITION BY label_unit, period ORDER BY price_at DESC, listing_id DESC
            ) > 1
                THEN 'superseded_in_label_month'
        END AS fate
    FROM r
    WINDOW label_month AS (PARTITION BY label_unit, period)
)
SELECT listing_id, label_unit, period, fate
FROM checked
WHERE fate IS NOT NULL

MODEL (
    name ledger.status,
    kind FULL,
    grain entry,
    audits (
        unique_values(columns := (entry)),
        not_null(columns := (entry, listing_id, change, status, differs))
    ),
    description 'Each entry of the corrections ledger, with its status against the kept rows.'
);

-- Each entry gets the first status that fits it, in this order:
--   retract     the entry undoes another.
--   retracted   a later entry undoes it.
--   absent      no kept row has its ad.
--   stale       a value in its `when` differs from the kept row's, or its `latest_ask` from the
--               ask analysis.latest_ask gives the row. `differs` names the values.
--   superseded  a later live set gives the same field of the same row.
--   live        it applies, and analysis.rows applies it.
WITH checked AS (
    SELECT e.entry, e.file, e.line, e.seq, e.listing_id, e.change, e.field,
        e.entry IN (SELECT retracts FROM ledger.entries WHERE change = 'retract') AS retracted,
        k.listing_id IS NOT NULL AS present,
        -- sqlglot renders concat_ws as NULL when any of its arguments is NULL, so the names
        -- join with ||.
        rtrim(
            CASE WHEN list_contains(e.when_keys, 'period')
                AND e.when_period <> strftime(k.period, '%Y-%m') THEN 'period ' ELSE '' END
            || CASE WHEN list_contains(e.when_keys, 'bedrooms')
                AND e.when_bedrooms IS DISTINCT FROM k.bedrooms THEN 'bedrooms ' ELSE '' END
            || CASE WHEN list_contains(e.when_keys, 'full_baths')
                AND e.when_full_baths IS DISTINCT FROM k.full_baths THEN 'full_baths ' ELSE '' END
            || CASE WHEN list_contains(e.when_keys, 'half_baths')
                AND e.when_half_baths IS DISTINCT FROM k.half_baths THEN 'half_baths ' ELSE '' END
            || CASE WHEN list_contains(e.when_keys, 'square_feet')
                AND e.when_square_feet IS DISTINCT FROM k.square_feet THEN 'square_feet ' ELSE '' END
            || CASE WHEN list_contains(e.when_keys, 'latest_ask')
                AND e.when_latest_ask IS DISTINCT FROM a.latest_ask THEN 'latest_ask ' ELSE '' END
        ) AS differs
    FROM ledger.entries e
    LEFT JOIN analysis.kept k USING (listing_id)
    LEFT JOIN analysis.latest_ask a USING (listing_id)
),
failed AS (
    SELECT *,
        CASE
            WHEN change = 'retract' THEN 'retract'
            WHEN retracted THEN 'retracted'
            WHEN NOT present THEN 'absent'
            WHEN differs <> '' THEN 'stale'
        END AS fails
    FROM checked
)
SELECT entry, file, line, listing_id, change, field,
    coalesce(fails, CASE
        WHEN change = 'set' AND row_number() OVER (
            PARTITION BY listing_id, field, fails IS NULL ORDER BY seq DESC
        ) > 1 THEN 'superseded'
        ELSE 'live'
    END) AS status,
    CASE WHEN present AND change <> 'retract' THEN differs ELSE '' END AS differs
FROM failed

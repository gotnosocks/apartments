MODEL (
    name ads.touched,
    kind FULL,
    grain listing_id,
    audits (unique_values(columns := (listing_id)), not_null(columns := (listing_id, incremental))),
    description 'The ads whose rows this build reads anew: every ad in a full build, the ads the new answers change in a top-up build.'
);

-- An ad's rows in the models of kind `merge` with `replace` change when the ad has a new answer
-- in ads.changes, or when a new answer holds a unit history listing an event of the ad. Such a
-- history counts one more answer, and its events may be new. In a full build ads.changes holds
-- every answer, so the table holds every ad with an answer or a history event. `incremental`
-- repeats the flag of ads.changes, so the models reading this table find it in one place.
WITH new AS (
    SELECT a.listing_id, a.history
    FROM ads.answers a
    SEMI JOIN ads.changes c USING (listing_id, response_id)
)
SELECT DISTINCT listing_id,
    (SELECT coalesce(bool_and(incremental), true) FROM ads.changes) AS incremental
FROM (
    SELECT listing_id::VARCHAR AS listing_id FROM new
    UNION ALL
    SELECT listing_id::VARCHAR
    FROM ads.history_events
    WHERE history IN (SELECT history FROM new WHERE history IS NOT NULL)
)

MODEL (
    name analysis.ask_check,
    kind FULL,
    grain listing_id,
    audits (
        unique_values(columns := (listing_id)),
        not_null(columns := (listing_id, latest_ask, peer_ask, peer_rows, ratio))
    ),
    description 'Each fit-ready row whose latest ask lies 6 to 16 times, or a sixteenth to a sixth of, the median latest ask of at least three other rows with the same building and bedroom count, for review.'
);

-- An error in every record of an ad leaves the latest-ask steps nothing to compare within the
-- ad, so a tenfold typo in all of an ad's prices passes into the rows. This check compares the
-- row's latest ask with the median latest ask of the building's other rows with the same
-- bedroom count, and lists the rows far from it for review. A typo of an extra or a missing
-- digit gives a ratio near 10. The band runs from 6 to 16 because the row's true ask can lie a
-- good way from its building's median: on the planted sample of Oct 16, the tenfold asks ran
-- from 6.8 to 15.1 times the median.
--
-- The check reads the fit-ready rows, after the corrections ledger: a live bedroom set puts a
-- row with the other rows of its corrected count, and an excluded ad leaves the peers. Every
-- row has a building and a bedroom count.
--
-- analysis.rows keeps the rows the check lists. On the export of Oct 16 the check listed 40
-- rows, and 3 of them were real asks and 3 the rents of income-restricted units, so a drop on
-- the ratio alone would select rows on the fit's target. A listed row leaves the rows through
-- a ledger exclude or set with its evidence, as any other row does.
WITH asks AS (
    SELECT k.listing_id, a.latest_ask,
        count(*) OVER (PARTITION BY k.building, k.bedrooms) - 1 AS peer_rows,
        median(a.latest_ask) OVER (
            PARTITION BY k.building, k.bedrooms
            ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING EXCLUDE CURRENT ROW
        ) AS peer_ask
    FROM analysis.rows k
    JOIN analysis.latest_ask a USING (listing_id)
)
SELECT listing_id, latest_ask, peer_ask, peer_rows, latest_ask / peer_ask AS ratio
FROM asks
WHERE peer_rows >= 3
    AND (latest_ask / peer_ask BETWEEN 6 AND 16 OR peer_ask / latest_ask BETWEEN 6 AND 16)

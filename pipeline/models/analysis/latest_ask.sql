MODEL (
    name analysis.latest_ask,
    kind FULL,
    grain listing_id,
    audits (
        unique_values(columns := (listing_id)),
        not_null(columns := (listing_id, price_at, first_ask, latest_ask, how)),
        every_row(rows := analysis.kept)
    ),
    description 'Each kept row''s latest ask and how it was chosen, as rentfrontier.latest_ask chooses it.'
);

-- The model reads the kept rows, before the corrections ledger, as the chain's chooser reads each
-- dataset before its correction rules. A change to the ledger leaves the latest asks as they are.
-- The checks against a row's building use the median log first ask among the building's other
-- rows with the same bedroom count. Every kept row has a building and a bedroom count. The steps
-- after s1 move the ask in turn:
--   s2: an ask more than twice or under half the first ask gives way to whichever of the two
--       lies nearer the building's median. When the first ask wins, or the building has no
--       median, the row takes the ad's last change within a factor of 2 of the first ask, so a
--       typo in the latest change leaves the changes before it in place.
--   s3 and s4 look at the ad's page price when its record was collected after the row.
--   s3: a page price within a factor of 2 of the ask replaces it. A page price equal to one of
--       the ad's price changes is skipped.
--   s4: when the page price is 9 to 11 times the ask, or the ask 9 to 11 times the page price,
--       whichever of the two lies nearer the building's median wins. A page price equal to a
--       change `ads.kept_changes` keeps is skipped, and one equal to a dropped change counts,
--       so a typo corrected on the ad's last day on the market gives way to the correction.
-- The median reads list positions with list_extract, counting from 1. SQLMesh renders each model
-- through sqlglot, and sqlglot 30.8 adds 1 to a computed index in brackets once it knows the
-- list's type.
WITH rows AS (
    SELECT listing_id, price_at, building, bedrooms, asking_rent, ln(asking_rent) AS log_rent
    FROM analysis.kept
),
grp AS (
    SELECT building, bedrooms, count(*) AS g, list_sort(list(log_rent)) AS v FROM rows
    WHERE building IS NOT NULL AND bedrooms IS NOT NULL GROUP BY ALL
),
ranked AS (
    SELECT r.*, g.g, g.v, row_number() OVER (PARTITION BY r.building, r.bedrooms ORDER BY r.log_rent) - 1 AS j
    FROM rows r LEFT JOIN grp g USING (building, bedrooms)
),
peer AS (
    SELECT listing_id, price_at, asking_rent AS first,
        CASE
            WHEN g IS NULL OR g < 2 THEN NULL
            WHEN g % 2 = 0 THEN CASE WHEN j <= g // 2 - 1 THEN list_extract(v, g // 2 + 1) ELSE list_extract(v, g // 2) END
            ELSE (CASE WHEN (g - 1) // 2 - 1 < j THEN list_extract(v, (g - 1) // 2) ELSE list_extract(v, (g - 1) // 2 + 1) END
                + CASE WHEN (g - 1) // 2 < j THEN list_extract(v, (g - 1) // 2 + 1) ELSE list_extract(v, (g - 1) // 2 + 2) END) / 2
        END AS peer
    FROM ranked
),
s1 AS (
    SELECT p.listing_id, p.price_at, p.first, p.peer, l.last, l.page_price AS page, l.digit_page,
        coalesce(l.near_first, p.first) AS near_first,
        coalesce(l.live, p.first) AS price,
        CASE WHEN l.live IS NOT NULL THEN 'latest' ELSE 'own ask, captured before the row' END AS how
    FROM peer p JOIN analysis.latest_change l USING (listing_id)
),
s2 AS (
    SELECT * EXCLUDE (wide, picked, near_first) REPLACE (
        CASE WHEN wide THEN picked ELSE price END AS price,
        CASE WHEN wide THEN CASE WHEN picked = first THEN 'first, nearer building'
            WHEN picked = near_first THEN 'earlier change, nearer building'
            ELSE 'latest, nearer building' END ELSE how END AS how)
    FROM (
        SELECT *, price / first > 2 OR price / first < 0.5 AS wide,
            CASE WHEN peer IS NOT NULL AND abs(ln(price) - peer) < abs(ln(first) - peer) THEN price ELSE near_first END AS picked
        FROM s1
    )
),
s3 AS (
    SELECT * EXCLUDE (near) REPLACE (
        CASE WHEN near THEN page ELSE price END AS price,
        CASE WHEN near AND page <> price THEN 'page price' ELSE how END AS how)
    FROM (SELECT *, coalesce(last AND page / price <= 2 AND price / page <= 2, false) AS near FROM s2)
),
s4 AS (
    SELECT * EXCLUDE (digit, picked, digit_page) REPLACE (
        CASE WHEN digit THEN picked ELSE price END AS price,
        CASE WHEN digit AND picked <> price THEN 'page price, digit' ELSE how END AS how)
    FROM (
        SELECT *, coalesce(last AND ((digit_page / price BETWEEN 9 AND 11) OR (price / digit_page BETWEEN 9 AND 11)), false) AS digit,
            CASE WHEN peer IS NULL THEN price WHEN abs(ln(digit_page) - peer) < abs(ln(price) - peer) THEN digit_page ELSE price END AS picked
        FROM s3
    )
)
SELECT listing_id, price_at, first AS first_ask, price AS latest_ask, how FROM s4

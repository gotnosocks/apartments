-- Current inventory: most recent observation for each listing
CREATE OR REPLACE VIEW current_inventory AS
SELECT l.*, s.observed_at, s.status, s.asking_rent, s.listed_date,
       s.days_on_market, s.scope
FROM listings l
JOIN listing_snapshots s USING (source, source_listing_id)
QUALIFY row_number() OVER (
  PARTITION BY source, source_listing_id ORDER BY observed_at DESC
) = 1;

-- Building summary
SELECT bedrooms, count(*) AS listings,
       round(median(asking_rent)) AS median_rent,
       round(median(asking_rent / nullif(square_feet, 0)), 2) AS median_rent_per_sqft
FROM current_inventory
WHERE canonical_address = '130 WEST 15 STREET'
GROUP BY bedrooms ORDER BY bedrooms;

-- Price changes inferred from repeated snapshots
WITH changes AS (
  SELECT source, source_listing_id, observed_at, asking_rent,
         lag(asking_rent) OVER (
           PARTITION BY source, source_listing_id ORDER BY observed_at
         ) AS prior_rent
  FROM listing_snapshots
)
SELECT *, asking_rent - prior_rent AS rent_change
FROM changes
WHERE asking_rent IS DISTINCT FROM prior_rent AND prior_rent IS NOT NULL
ORDER BY observed_at DESC;

-- Provider-supplied listing events
SELECT l.canonical_address, l.unit, e.event_at, e.event_type, e.price
FROM listing_events e
JOIN listings l USING (source, source_listing_id)
ORDER BY e.event_at DESC;

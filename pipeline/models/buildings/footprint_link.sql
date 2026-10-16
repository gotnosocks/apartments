MODEL (
    name buildings.footprint_link,
    kind FULL,
    grain building_id,
    audits (
        unique_values(columns := (building_id)),
        not_null(columns := (building_id, footprints_release, bbl, inside, metres, lots_inside))
    ),
    description 'Each building whose map point falls in a footprint of the latest footprints copy, or within 10 m of one: that footprint''s BIN and lot.'
);

-- The step finds the footprints around each building's map point and tests the point against
-- each one. It works in these steps:
--
-- 1. It reads the corners of each footprint from its WKT text and widens the box around them by
--    15 m on each side: 0.000136 degrees of latitude and 0.00018 of longitude, at New York's
--    latitude.
-- 2. It lists the cells of 0.001 degrees each box covers, and pairs each point with the boxes
--    covering its own cell and holding it.
-- 3. For each pair, it counts the edges a ray from the point toward the east crosses, over every
--    ring of the footprint. An odd count puts the point inside. It also measures the distance
--    from the point to the nearest edge, in metres, from degrees scaled by 110,574 m for
--    latitude and by 111,320 m times the cosine of the latitude for longitude.
-- 4. It keeps the footprints holding the point, or else the nearest within 10 m, and takes the
--    first by distance to an edge and then by its place in the copy.
--
-- `bbl` is the footprint's `mappluto_bbl`, which gives a condominium's billing lot, as MapPLUTO
-- does. `lots_inside` counts the lots of the footprints holding the point, which is more than one
-- where footprints overlap.
WITH copy AS (
    SELECT arg_max(release, published) AS release FROM city.footprints
), points AS (
    SELECT building_id, longitude AS lon, latitude AS lat,
        floor(longitude * 1000)::BIGINT AS cx, floor(latitude * 1000)::BIGINT AS cy
    FROM buildings.latest_record
    WHERE longitude IS NOT NULL AND latitude IS NOT NULL
), numbers AS (
    SELECT record, bin, mappluto_bbl,
        list_transform(regexp_extract_all(the_geom, '-?\d+(?:\.\d+)?'), x -> x::DOUBLE) AS v
    FROM city.footprints
    WHERE release = (SELECT release FROM copy)
), boxes AS (
    SELECT record, bin, mappluto_bbl,
        list_min(list_filter(v, (x, i) -> i % 2 = 1)) - 0.00018 AS x0,
        list_max(list_filter(v, (x, i) -> i % 2 = 1)) + 0.00018 AS x1,
        list_min(list_filter(v, (x, i) -> i % 2 = 0)) - 0.000136 AS y0,
        list_max(list_filter(v, (x, i) -> i % 2 = 0)) + 0.000136 AS y1
    FROM numbers
), cells AS (
    SELECT b.record, b.x0, b.x1, b.y0, b.y1, x AS cx, y AS cy
    FROM boxes b,
        range(floor(b.x0 * 1000)::BIGINT, floor(b.x1 * 1000)::BIGINT + 1) a(x),
        range(floor(b.y0 * 1000)::BIGINT, floor(b.y1 * 1000)::BIGINT + 1) c(y)
), near AS (
    SELECT p.building_id, p.lon, p.lat, c.record
    FROM points p JOIN cells c USING (cx, cy)
    WHERE p.lon BETWEEN c.x0 AND c.x1 AND p.lat BETWEEN c.y0 AND c.y1
), rings AS (
    SELECT f.record, r.ring, r.i AS ring_i
    FROM city.footprints f,
        unnest(regexp_extract_all(f.the_geom, '\(([^()]+)\)', 1)) WITH ORDINALITY r(ring, i)
    WHERE f.release = (SELECT release FROM copy)
        AND f.record IN (SELECT record FROM near)
), corners AS (
    SELECT record, ring_i, c.i AS k,
        split_part(trim(c.xy), ' ', 1)::DOUBLE AS x, split_part(trim(c.xy), ' ', 2)::DOUBLE AS y
    FROM rings, unnest(string_split(ring, ',')) WITH ORDINALITY c(xy, i)
), edges AS (
    SELECT record, x AS xa, y AS ya, lead(x) OVER w AS xb, lead(y) OVER w AS yb
    FROM corners
    WINDOW w AS (PARTITION BY record, ring_i ORDER BY k)
    QUALIFY xb IS NOT NULL
), scaled AS (
    SELECT n.building_id, n.record, n.lon, n.lat, e.xa, e.ya, e.xb, e.yb,
        111320 * cos(radians(n.lat)) AS kx, 110574.0 AS ky
    FROM near n JOIN edges e USING (record)
), projected AS (
    SELECT *,
        greatest(0, least(1,
            CASE WHEN power(kx * (xb - xa), 2) + power(ky * (yb - ya), 2) = 0 THEN 0
            ELSE (kx * kx * (lon - xa) * (xb - xa) + ky * ky * (lat - ya) * (yb - ya))
                / (power(kx * (xb - xa), 2) + power(ky * (yb - ya), 2)) END)) AS t
    FROM scaled
), tested AS (
    SELECT building_id, record,
        sum((((ya > lat) <> (yb > lat))
            AND lon < (xb - xa) * (lat - ya) / (yb - ya) + xa)::INTEGER) % 2 = 1 AS inside,
        min(sqrt(power(kx * (lon - (xa + t * (xb - xa))), 2)
            + power(ky * (lat - (ya + t * (yb - ya))), 2))) AS metres
    FROM projected
    GROUP BY building_id, record
), kept AS (
    SELECT t.*, b.bin, b.mappluto_bbl AS bbl
    FROM tested t JOIN boxes b USING (record)
    WHERE t.inside OR t.metres <= 10
), chosen AS (
    SELECT building_id,
        arg_min({'bbl': bbl, 'bin': bin, 'metres': metres}, (NOT inside, metres, record)) AS pick,
        bool_or(inside) AS inside,
        count(DISTINCT bbl) FILTER (WHERE inside) AS lots_inside
    FROM kept
    GROUP BY building_id
)
SELECT building_id, (SELECT release FROM copy) AS footprints_release, pick.bbl, pick.bin, inside,
    pick.metres, lots_inside
FROM chosen

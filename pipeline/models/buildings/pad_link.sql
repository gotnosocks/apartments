MODEL (
    name buildings.pad_link,
    kind FULL,
    grain building_id,
    audits (
        unique_values(columns := (building_id)),
        not_null(columns := (building_id, pad_release, bbl, bin, rank, lots))
    ),
    description 'Each building whose address falls in an address range of the latest PAD release: the lot and BIN of the best range, and how well it matched.'
);

-- The step cuts each building's street address into a house number, a letter and a street
-- name, and looks the street up in the latest PAD release's street name dictionary, which gives
-- every name of a street under the street's code. The ranges of `bobaadr` give a street by its
-- code, so `6th Avenue` finds the ranges of AVENUE OF THE AMERICAS. The parse works in these
-- steps:
--
-- 1. It drops periods, commas and apostrophes, turns the address to capitals and collapses its
--    spaces.
-- 2. It reads a house number, perhaps a second number after a hyphen, perhaps a letter, perhaps
--    `1/2`, and the street name. `3-5 Hudson Street` gives 3 and 5, `94A Gates Avenue` and
--    `94 A Gates Avenue` give 94 and A, and `381 1/2 Union Street` gives 381 and a half. After a
--    space, E, N, S or W starts the street's name, as in `135 W 89th Street`.
-- 3. It drops the ordinal suffix of each number in the street name, so `89th` reads as 89, as
--    PAD writes it.
-- 4. It spells out a leading E, W, N or S, and a last word abbreviated as in the list below.
--
-- The borough comes from the record's community district, whose first digit is the borough's
-- code, and else from the city of the address.
--
-- PAD sorts house numbers by an 11-character key: a flag for a Queens number with a hyphen, the
-- number before the hyphen in five digits, the number after it in three, and a code for a
-- trailing letter or a half, AA for none. A Queens address with a hyphen, as in
-- `37-16 30th Street`, gives a single key. Elsewhere, a hyphen gives a range of house numbers,
-- and the step tries each end. A letter A to I takes the code M and the letter after it (A gives
-- MB), J to R takes N and the letter eight places before it (J gives NB), and S to Z takes O and
-- the letter sixteen places before it (S gives OC). The rule agrees with every PAD range of 26c
-- whose number ends in one letter. A half takes AH.
--
-- A range matches a try when its street code and its borough are the try's, the try's first
-- nine characters fall between those of the range's low and high keys, and the range's side of
-- the street, odd or even, is the try's or both. Of the matching ranges, the step keeps the
-- ones of lowest rank. The rank adds
--
-- - 8 when the try's whole key, letter code included, falls outside the range, as `94A` against
--   a range of 94 alone,
-- - 4 when the range's low number differs from the address's number, letter and half,
-- - 2 when the range holds a vanity address (V) or a range of numbers kept for one building (Q)
--   rather than a plain address,
-- - 1 when the range's zip differs from the address's.
--
-- A condominium's ranges give the lot of one of its units, and `bobabbl` gives each unit lot
-- its billing lot. The step reports the billing lot, as MapPLUTO and the footprints do. Where
-- the ranges of lowest rank give several lots, the step takes the lowest and counts them in
-- `lots`. BIN 1000000, 2000000 and so on stand for a lot without a numbered building, and the
-- step takes another BIN of the lot first.
WITH pad AS (
    SELECT arg_max(release, published) AS release FROM city.pad_addresses
), suffixes(abbr, word) AS (
    VALUES ('ST', 'STREET'), ('STR', 'STREET'), ('AVE', 'AVENUE'), ('AV', 'AVENUE'),
        ('PL', 'PLACE'), ('BLVD', 'BOULEVARD'), ('BL', 'BOULEVARD'), ('RD', 'ROAD'),
        ('LN', 'LANE'), ('TER', 'TERRACE'), ('TERR', 'TERRACE'), ('PKWY', 'PARKWAY'),
        ('CT', 'COURT'), ('SQ', 'SQUARE'), ('DR', 'DRIVE'), ('HWY', 'HIGHWAY'), ('PLZ', 'PLAZA'),
        ('CIR', 'CIRCLE'), ('EXPY', 'EXPRESSWAY'), ('WY', 'WAY')
), cleaned AS (
    SELECT building_id, zip,
        trim(regexp_replace(regexp_replace(upper(street), '[.,'']', '', 'g'), '\s+', ' ', 'g'))
            AS street,
        CASE WHEN left(community_district, 1) IN ('1', '2', '3', '4', '5')
                THEN left(community_district, 1)
            WHEN upper(city) IN ('NEW YORK', 'MANHATTAN') THEN '1'
            WHEN upper(city) = 'BRONX' THEN '2'
            WHEN upper(city) IN ('BROOKLYN', 'WILLIAMSBURG') THEN '3'
            WHEN upper(city) IN ('QUEENS', 'RIDGEWOOD', 'LONG ISLAND CITY', 'ASTORIA') THEN '4'
            WHEN upper(city) = 'STATEN ISLAND' THEN '5' END AS boro
    FROM buildings.latest_record
), parts AS (
    SELECT building_id, zip, boro,
        regexp_extract(street, '^(\d+)(?:-(\d+))?([A-Z]| [A-DF-MO-RT-VX-Z])?( 1/2)? (.+)$', 1) AS n1,
        regexp_extract(street, '^(\d+)(?:-(\d+))?([A-Z]| [A-DF-MO-RT-VX-Z])?( 1/2)? (.+)$', 2) AS n2,
        trim(regexp_extract(street, '^(\d+)(?:-(\d+))?([A-Z]| [A-DF-MO-RT-VX-Z])?( 1/2)? (.+)$', 3))
            AS letter,
        regexp_extract(street, '^(\d+)(?:-(\d+))?([A-Z]| [A-DF-MO-RT-VX-Z])?( 1/2)? (.+)$', 4) <> '' AS half,
        regexp_replace(
            regexp_extract(street, '^(\d+)(?:-(\d+))?([A-Z]| [A-DF-MO-RT-VX-Z])?( 1/2)? (.+)$', 5),
            '\b(\d+)(ST|ND|RD|TH)\b', '\1', 'g') AS name
    FROM cleaned
), named AS (
    SELECT p.building_id, p.zip, p.boro, p.n1, p.n2, p.letter, p.half,
        concat_ws(' ',
            CASE regexp_extract(p.name, '^([EWNS]) ', 1)
                WHEN 'E' THEN 'EAST' WHEN 'W' THEN 'WEST' WHEN 'N' THEN 'NORTH'
                WHEN 'S' THEN 'SOUTH' END,
            CASE WHEN s.word IS NULL THEN regexp_replace(p.name, '^[EWNS] ', '')
                ELSE regexp_replace(regexp_replace(p.name, '^[EWNS] ', ''), ' \S+$', ' ' || s.word)
                END) AS name
    FROM parts p
    LEFT JOIN suffixes s ON s.abbr = regexp_extract(p.name, ' (\S+)$', 1)
    WHERE p.n1 <> '' AND p.boro IS NOT NULL
), tries AS (
    SELECT n.building_id, n.zip, n.boro, n.name, n.letter, n.half, t.number,
        CASE WHEN n.boro = '4' AND n.n2 <> ''
                THEN '1' || lpad(n.n1, 5, '0') || lpad(n.n2, 3, '0')
            ELSE '0' || lpad(t.number, 5, '0') || '000' END
        || CASE WHEN n.letter = '' AND n.half THEN 'AH'
            WHEN n.letter = '' THEN 'AA'
            WHEN n.letter BETWEEN 'A' AND 'I' THEN 'M' || chr(ascii(n.letter) + 1)
            WHEN n.letter BETWEEN 'J' AND 'R' THEN 'N' || chr(ascii(n.letter) - 8)
            ELSE 'O' || chr(ascii(n.letter) - 16) END AS key,
        CASE WHEN n.boro = '4' AND n.n2 <> '' THEN n.n2 ELSE t.number END::INTEGER % 2 AS odd
    FROM named n, unnest(
        CASE WHEN n.boro = '4' AND n.n2 <> '' THEN [n.n1 || '-' || n.n2]
            WHEN n.n2 <> '' THEN [n.n1, n.n2]
            ELSE [n.n1] END
    ) t(number)
), streets AS (
    SELECT DISTINCT boro, trim(regexp_replace(name, '\s+', ' ', 'g')) AS name, sc5
    FROM city.pad_streets, unnest([stname, full_stname]) t(name)
    WHERE release = (SELECT release FROM pad)
), ranges AS (
    SELECT boro, block, lot, bin, scboro, sc5, parity, addrtype, zipcode, trim(lhnd) AS lhnd,
        lhns, hhns
    FROM city.pad_addresses
    WHERE release = (SELECT release FROM pad) AND addrtype IN (' ', 'V', 'Q')
), billing AS (
    SELECT loboro || loblock || lolot AS lot,
        CASE WHEN condoflag = 'C' THEN billboro || billblock || billlot END AS billing
    FROM city.pad_lots
    WHERE release = (SELECT release FROM pad)
), hits AS (
    SELECT t.building_id, r.bin,
        coalesce(b.billing, r.boro || r.block || r.lot) AS bbl,
        (t.key NOT BETWEEN r.lhns AND r.hhns)::INTEGER * 8
            + (r.lhnd <> (t.number || t.letter || CASE WHEN t.half THEN ' 1/2' ELSE '' END))::INTEGER * 4
            + (r.addrtype <> ' ')::INTEGER * 2
            + (r.zipcode IS DISTINCT FROM t.zip)::INTEGER AS rank
    FROM tries t
    JOIN streets s ON s.boro = t.boro AND s.name = t.name
    JOIN ranges r ON r.scboro = t.boro AND r.sc5 = s.sc5
        AND left(t.key, 9) BETWEEN left(r.lhns, 9) AND left(r.hhns, 9)
        AND (r.parity = CASE t.odd WHEN 1 THEN '1' ELSE '2' END OR r.parity = '0')
    LEFT JOIN billing b ON b.lot = r.boro || r.block || r.lot
), best AS (
    SELECT * FROM hits QUALIFY rank = min(rank) OVER (PARTITION BY building_id)
)
SELECT building_id, (SELECT release FROM pad) AS pad_release,
    min(bbl) AS bbl,
    arg_min(bin, (bbl, bin LIKE '_000000', bin)) AS bin,
    min(rank) AS rank,
    count(DISTINCT bbl) AS lots
FROM best
GROUP BY building_id

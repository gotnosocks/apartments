MODEL (
    name analysis.building_certificates,
    kind FULL,
    grain listing_id,
    audits (unique_values(columns := (listing_id)), not_null(columns := (listing_id))),
    description 'Each candidate ad''s BIN, with the certificates of occupancy DOB had issued on it by the ad''s first day: the first of a new building, the latest major alteration and the latest count of apartments.'
);

-- The step reads the latest copy of each of DOB's two sets of certificates of occupancy:
--
-- - `city.dob_co`, the earlier set, from July 2012, a row for each certificate of a job,
-- - `city.dob_now_co`, the DOB NOW set, from March 2021, with renewals of earlier jobs too.
--
-- A job and its certificates can appear in both sets, so the step reads each job's certificates
-- from both and dates the job by its first certificate. Both sets hold only new buildings and
-- major alterations (Alteration Type 1). These values stop the build, so a change in either
-- set's spelling shows up here rather than as a missing certificate:
--
-- - a job type outside the two kinds,
-- - an issue date that is blank in `city.dob_co`, or isn't written in the set's form: a
--   four-digit year, month, day and time in `city.dob_co`, and month, day, two-digit year and
--   time in `city.dob_now_co`.
--
-- DOB NOW files a building rebuilt behind walls it keeps as a new building with existing
-- elements to remain, and the step counts it as a new building, as DOB does. The earlier set
-- has no such type, so a rebuild before DOB NOW reads as a plain new building job.
--
-- A certificate in `city.dob_now_co` without an issue date stays out, since nothing dates it.
-- A count of apartments other than a whole number reads as missing. A date after the copy, like
-- the 2105 of a 2015 certificate in `city.dob_co`, falls after every ad and never counts.
--
-- For each candidate ad it takes the BIN of its building from `buildings.lots` and dates the ad
-- by its first day in UTC. A BIN such as 1000000 stands for a lot without a numbered building,
-- and the step reads it as no BIN. It keeps the BIN's jobs with a first certificate on or before that
-- day:
--
-- - `new_building_since`: the first certificate of the earliest new building job,
-- - `altered_since`: the first certificate of the latest major alteration job,
-- - `units`: the count of apartments on the latest certificate giving one, and on a day with
--   certificates in both sets, the DOB NOW one.
--
-- Each comes with the job or certificate behind it. `new_building` and `altered` say whether the
-- BIN had such a job, and stay missing for an ad without a BIN or without a copy of each set.
-- The earlier set begins in July 2012, so a building finished before then has no new building
-- job, unless DOB issued a certificate on its job after July 2012, such as a renewal of a
-- temporary certificate. Then `new_building_since` gives the first of those, years after the
-- building went up.
-- `dob_co_release` and `dob_now_co_release` give the copies each row read.
WITH dob_co AS (
    SELECT arg_max(release, published) AS release FROM city.dob_co
), dob_now_co AS (
    SELECT arg_max(release, published) AS release FROM city.dob_now_co
), earlier AS (
    SELECT c.* FROM (
        SELECT * FROM (
            SELECT NULL::TEXT AS bin_number, NULL::TEXT AS job_number, NULL::TEXT AS item_number,
                NULL::TEXT AS job_type, NULL::TEXT AS c_o_issue_date,
                NULL::TEXT AS pr_dwelling_unit
            WHERE false
        ) UNION ALL BY NAME (SELECT * FROM city.dob_co)
    ) c
    JOIN dob_co USING (release)
), later AS (
    SELECT c.* FROM (
        SELECT * FROM (
            SELECT NULL::TEXT AS bin, NULL::TEXT AS job_filing_name, NULL::TEXT AS c_of_o_number,
                NULL::TEXT AS job_type, NULL::TEXT AS c_of_o_issuance_date,
                NULL::TEXT AS number_of_dwelling_units
            WHERE false
        ) UNION ALL BY NAME (SELECT * FROM city.dob_now_co)
    ) c
    JOIN dob_now_co USING (release)
), certificates AS (
    SELECT 'dob_co' AS source, trim(bin_number) AS bin, trim(job_number) AS job,
        concat(trim(job_number), ' item ', trim(item_number)) AS certificate,
        CASE trim(job_type)
            WHEN 'NB' THEN 'new_building'
            WHEN 'A1' THEN 'alteration'
            ELSE error(concat('job type ', job_type, ' of job ', job_number, ' in dob_co'))::TEXT
            END AS kind,
        CASE WHEN nullif(trim(c_o_issue_date), '') IS NULL
            THEN error(concat('no issue date for job ', job_number, ' in dob_co'))::DATE
            WHEN NOT regexp_full_match(
                trim(c_o_issue_date), '[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}[.][0-9]{3}'
            )
            THEN error(
                concat('issue date ', c_o_issue_date, ' of job ', job_number, ' in dob_co')
            )::DATE
            ELSE strptime(trim(c_o_issue_date), '%Y-%m-%dT%H:%M:%S.%g')::DATE
            END AS issued,
        CASE WHEN regexp_full_match(trim(pr_dwelling_unit), '[0-9]+')
            THEN trim(pr_dwelling_unit)::INTEGER END AS units
    FROM earlier
    UNION ALL
    SELECT 'dob_now_co', trim(bin), trim(job_filing_name), trim(c_of_o_number),
        CASE trim(job_type)
            WHEN 'NEW BUILDING' THEN 'new_building'
            WHEN 'New Building' THEN 'new_building'
            WHEN 'CO - New Building with Existing Elements to Remain' THEN 'new_building'
            WHEN 'ALTERATION TYPE 1' THEN 'alteration'
            WHEN 'Alteration CO' THEN 'alteration'
            ELSE error(
                concat('job type ', job_type, ' of job ', job_filing_name, ' in dob_now_co')
            )::TEXT
            END,
        CASE WHEN NOT regexp_full_match(
                trim(c_of_o_issuance_date),
                '[0-9]{2}/[0-9]{2}/[0-9]{2} +[0-9]{1,2}:[0-9]{2}:[0-9]{2} [AP]M'
            )
            THEN error(concat(
                'issue date ', c_of_o_issuance_date, ' of certificate ', c_of_o_number,
                ' in dob_now_co'
            ))::DATE
            ELSE strptime(
                regexp_replace(trim(c_of_o_issuance_date), ' +', ' ', 'g'),
                '%m/%d/%y %I:%M:%S %p'
            )::DATE
            END,
        CASE WHEN regexp_full_match(trim(number_of_dwelling_units), '[0-9]+')
            THEN trim(number_of_dwelling_units)::INTEGER END
    FROM later
    WHERE nullif(trim(c_of_o_issuance_date), '') IS NOT NULL
), jobs AS (
    SELECT bin, job, kind, min(issued) AS first_issued
    FROM certificates
    GROUP BY ALL
), ads AS (
    SELECT c.listing_id, c.building_id, (c.price_at AT TIME ZONE 'UTC')::DATE AS first_day,
        CASE WHEN l.bin NOT LIKE '_000000' THEN l.bin END AS bin
    FROM analysis.candidates c
    LEFT JOIN buildings.lots l USING (building_id)
), days AS (
    SELECT DISTINCT bin, first_day FROM ads WHERE bin IS NOT NULL
), held AS (
    SELECT d.bin, d.first_day,
        min(j.first_issued) FILTER (WHERE j.kind = 'new_building') AS new_building_since,
        arg_min(j.job, (j.first_issued, j.job)) FILTER (WHERE j.kind = 'new_building')
            AS new_building_job,
        max(j.first_issued) FILTER (WHERE j.kind = 'alteration') AS altered_since,
        arg_max(j.job, (j.first_issued, j.job)) FILTER (WHERE j.kind = 'alteration')
            AS alteration_job
    FROM days d
    JOIN jobs j ON j.bin = d.bin AND j.first_issued <= d.first_day
    GROUP BY ALL
), counted AS (
    SELECT d.bin, d.first_day,
        arg_max(c.units, (c.issued, c.source, c.certificate)) AS units,
        max(c.issued) AS units_issued,
        arg_max(c.source, (c.issued, c.source, c.certificate)) AS units_source,
        arg_max(c.certificate, (c.issued, c.source, c.certificate)) AS units_certificate
    FROM days d
    JOIN certificates c ON c.bin = d.bin AND c.issued <= d.first_day AND c.units IS NOT NULL
    GROUP BY ALL
)
SELECT a.listing_id, a.building_id, a.bin, a.first_day,
    dob_co.release AS dob_co_release, dob_now_co.release AS dob_now_co_release,
    CASE WHEN a.bin IS NOT NULL AND dob_co.release IS NOT NULL
        AND dob_now_co.release IS NOT NULL
        THEN h.new_building_since IS NOT NULL END AS new_building,
    CASE WHEN a.bin IS NOT NULL AND dob_co.release IS NOT NULL
        AND dob_now_co.release IS NOT NULL
        THEN h.altered_since IS NOT NULL END AS altered,
    h.new_building_since, h.new_building_job, h.altered_since, h.alteration_job,
    u.units, u.units_issued, u.units_source, u.units_certificate
FROM ads a
CROSS JOIN dob_co
CROSS JOIN dob_now_co
LEFT JOIN held h USING (bin, first_day)
LEFT JOIN counted u USING (bin, first_day)

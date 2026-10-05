# Ratings: design

Ben's own notes on listings (2026-10-05): a score, appealing and unappealing tags and a note on
each listing page, a My ratings page, and a CSV/JSON export. Tailnet only.

## Storage

- One SQLite file outside the site builds: `/data1/apartments/ratings/ratings.sqlite`
  (`RATINGS_DB` overrides it; tests use a temp file). A site build replaces `site/current`, so
  ratings can't live in the build database. WAL mode, one short write per request.
- `ratings`: one row per listing, keyed by `audit_id`, with `unit_id` and `building_id` so the
  unit and building pages can show it. Fields: `score` (1–5 or empty), `tags` (JSON list),
  `note` (up to 2,000 characters), `created_at`, `updated_at`. It also keeps a `snapshot` (JSON)
  of what the listing showed when it was rated: address, unit, layout, ask, estimate, likely ask
  range and build id. The export stays readable after the listing leaves a later build.
- `rating_events`: every save appended (audit_id, time, the new values). An edit or a clear
  never loses an earlier note.

## Tags

A fixed list, so they can be counted and filtered, plus free-text tags. Stored with their side
("+light", "-building"), since "building" and "price" can be either.

- Appealing: light, quiet, layout, kitchen, closets, outdoor space, laundry, views, block,
  building, price.
- Unappealing: dark, noisy, small, awkward layout, walk-up, needs work, no laundry, avenue,
  building, price.

## Pages

- **Listing page:** a "Your rating" card under the verdict. It has a 1–5 score (radio buttons), the
  tags as two groups of checkboxes, a free-text tags field, a note and a Save button. It is a
  plain HTML form POST and redirect, with no JavaScript, so the CSP is unchanged. A saved rating
  shows as a summary with an Edit link. Listing tables, the unit page's included, mark a rated
  listing with ★ and its score.
- **My ratings** (`/ratings`, in the Estimates nav): a table with the score, listing, tags, the
  note's first line, the ask and estimate when rated, and where the listing stands in the current
  build. It sorts by score, date and ask vs estimate, and filters by tag and minimum score.
- **Export:** `/ratings.csv` and `/ratings.json`, every field plus the snapshot.

## Tailnet only and writes

- The site already listens only on the tailnet address and localhost, with trusted hosts set.
  Writes also check that the request comes from a tailnet (100.64.0.0/10) or loopback address,
  and that the `Origin` (or `Referer`) is one of the allowed hosts, so another page can't post a
  rating. There are no accounts: one rater, Ben.
- The site process opens the ratings file read-write and the build read-only, as now.

## Not in the first PR

- Using the ratings in the model or for recommendations.
- More than one rater.

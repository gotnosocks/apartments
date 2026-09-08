# Chelsea cloud preparation, September 8, 2026

Snapshot `chelsea-20260908` preserves the uploaded archive and its collection
timestamps in Modal Volume `chelsea-archive`. The complete transfer included
6,301 compressed page bodies and the 7,371,026,432-byte SQLite archive.

The CPU worker completed import, building audit, and monthly preparation in
37.28 seconds. It examined 4,192 listing snapshots, skipped 4,189 already handled
captures, imported three additional captures with 17 historical events, and
reported zero failures. Prepared-file SHA-256:
`4e8d647f1c22ae9397e51d619886c0152da76e5fdd9c54777b9601b833320f83`.

The imported rental data contains 17,783 deduplicated events across 715 source
unit labels and 165 buildings. The model input contains 4,023 monthly observations,
661 labels and 149 buildings after existing exclusions. Source labels can include
aliases and legacy identifiers; they are not verified distinct physical units.

Streaming the latest root building pages identified 479 entries classified as
Rental building, with 19,029 reported residential units. This is the sum of source
building attributes, not a count of scraped rental histories, listings, or verified
unique physical units. Condo, co-op, and other building types are reported separately
in `buildings.jsonl` and preparation metadata. These figures demonstrate why
165 buildings with imported rental history cannot describe full Chelsea coverage.

The saved scoped queue still has 3,047 pending and five interrupted in-flight URLs;
the remote scraper will recover those in-flight entries on resume. Neither the
archive nor this model input claims exhaustive historical coverage. The local
archive browser continues to show the local copy, not new cloud captures.

Prepared artifacts are under `/snapshots/chelsea-20260908/prepared/` in Modal and
downloaded to `data/model/prepared/chelsea-20260908/` for inspection. Future cloud
scrapes must publish a new snapshot before preparation and fitting.

# Immutable recovery of archived listing descriptions

Some StreetEasy captures store the description as a React Flight reference such as `$3f`. The text exists in a byte-framed `3f:T<hex-length>,<text>` record in the same archived HTML. Resolving that record is a new interpretation of an existing capture; it is not a new market observation or proof of an attribute's historical effective date.

Run offline recovery with:

```sh
uv run --locked python -m apartments.description_recovery \
  /data1/apartments/archive/datasets/chelsea-granular-20260917-canonical-url-v1 \
  /data1/apartments/archive/bodies \
  data/exports/chelsea-description-recovery-20260918 \
  --workers 4 --batch-size 64
```

The recovery process never scrapes or modifies archive bodies/source tables. It scans rental payloads with unresolved hexadecimal references, verifies the decompressed captured body's SHA256, reparses the captured URL, and accepts only a matching listing/canonical identity whose raw payload changes exclusively at `/description`. Missing bodies, malformed or oversized captures, identity disagreements, unresolved descriptions, and changes to other source fields go to quarantine with a reason. Maximum decompressed input is 32 MiB per worker; a body reaching that cap is rejected. Worker count is bounded to eight and defaults to four, with only a bounded batch queued. Parser/library memory adds overhead beyond the decompressed input bound.

Each accepted record retains the snapshot ID, listing ID, captured URL and canonical unit URL, body hash, original raw listing hash, original reference, recovered literal description and its hash, reparsed payload hash, original observation timestamp, actual UTC interpretation timestamp, and version identifiers. Recovered text does not bypass attribute extraction's uncertainty or negation handling.

`complete.json` is a `research_pipeline.read_bundle` compatible manifest. It hashes `accepted.jsonl`, `quarantined.jsonl`, `source-files.json`, and `coverage.json`, and records implementation/runtime versions. `source-files.json` hashes every consumed listing/snapshot parquet shard and the canonical dataset completion marker. The aggregate source manifest hash uses sorted compact UTF-8 JSON. Completion is published last, after final source and implementation hash checks.

Progress is committed in content-hashed batch checkpoints. Repeating the identical command reuses completed batches and their original interpretation timestamps. An interrupted, uncommitted batch can be retried. Changed source/configuration/implementation or corrupt checkpoints fail closed; choose a new output directory after intentional implementation changes. A completed run verifies and reuses its artifacts. No partially completed bundle should be consumed by a model.

Downstream integration must independently verify the bundle hashes and source inventory, bind each recovery to the exact snapshot body hash/original raw payload hash/reference/listing identity, and apply it only when `interpreted_at` is at or before the analytical knowledge cutoff. Keep the original capture payload and recovery provenance in the analytical audit. The historical pricing target remains the same advertisement's initial asking event; later interpretation does not make this a contemporaneous historical dataset.

## Chelsea recovery on 2026-09-18

The full canonical-source run completed at `2026-09-18T15:15:56.429823+00:00`. All **27,240 unresolved rental captures** recovered successfully, covering **19,440 distinct listing IDs**; no candidates were quarantined. The maximum row interpretation timestamp is `2026-09-18T15:15:55.292750+00:00`. Each accepted row passed the archived-body hash, listing/canonical identity, and description-only change checks. The run committed 426 batches and an identical rerun verified/reused the same completed manifest.

The local bundle is `data/exports/chelsea-description-recovery-20260918`. Its accepted artifact SHA256 is `81c99e00c1e562cddbeb87787d981a465068ef77401689e17e589d55e642b9f5`; its aggregate source manifest SHA256 is `5e0d5fe3448ae9015937bbf2a76168d5f23accb6da474715aee2e773dc5f9e1b`. This establishes text recovery, not the correctness of every amenity assertion in marketing descriptions.

After this completed run, checkpoint replay was corrected to split JSONL only at literal LF record delimiters. Recovered text can legitimately contain literal Unicode U+2028, U+2029, and U+0085 characters; Python `str.splitlines()` also splits at those characters and could break an interrupted resume. A regression now interrupts and resumes a batch containing all three, preserving the text and original interpretation timestamp. Both checkpoint replay and final artifact assembly use LF-delimited file iteration.

The completed 2026-09-18 bundle remains unchanged and valid under its recorded implementation hash. This subsequent code change deliberately changes the current implementation hash: use a fresh recovery output directory for a new build, and continue consuming the existing completed bundle through hash verification rather than attempting to rebuild it with the updated implementation.

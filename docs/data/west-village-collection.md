# West Village rental collection

`--neighborhood west-village --rental-canonical-only` enables a persistent
rental collection policy. Use a separate archive from Chelsea. This flag is
opt-in; existing crawl policies do not change automatically.

Sale routes, sales inventories, and unsupported advertisement-ID routes are
excluded before provider submission. A canonical unit route may be probed to
establish its identity and rental evidence. Explicit rental advertisement IDs
must have exactly one canonical-unit association, supported by the rental
history of a successfully parsed canonical unit page. Advertisement pages cannot
recursively authorize other advertisements. Missing or conflicting canonical
links, ambiguous listing payloads, and sale-only histories prevent further
expansion; they remain archived evidence, not accepted analytical observations.
Historical advertisements still need their own captured attributes: current
unit attributes are not projected backward onto old prices.

`collection_memberships` records source URL and body hash;
`collection_exclusions` records skipped URLs and reasons. Later canonical evidence
may unlock a previously unknown advertisement, retaining the exclusion audit.
Resume reuses archived bytes without paid requests. Raw snapshots are never
removed or rewritten by the policy. Existing exact-advertisement alias reuse
continues to require successful full-detail evidence.

The September 19 run is `apartments-west-village-low-rate-20260919-v5.service`.
Archive: `/data1/apartments/archive/crawls/west-village-low-rate-20260919`.
The fixed runtime and resume script are under
`data/probes/west-village-20260919/`. The user subsequently removed both the
300-attempt cap and morning cutoff, authorizing collection until Oxylabs credits
are exhausted. Keep one worker and at most one submission every 30 seconds,
including retries. `--max-requests 0` is unlimited; systemd has no runtime limit.
Stop on provider account/payment rejection (HTTP 401/402/403), source blocking,
or completion of the eligible queue. The service has no automatic restart;
do not restart account/payment failures or purchase/refill credits automatically.
Other temporary failures can be reviewed by the hourly improvement follow-up.

Offline replay before the policy restart found 74 mapped rental advertisement
IDs. Of 179 scoped outstanding URLs, 57 lacked canonical-unit association and
one was a sale route; 121 remained eligible for discovery. Eleven saved listing
captures failed the stricter eligibility check. These are coverage exclusions,
not proof that the source has no additional eligible rentals.

## September 20 first hourly efficiency review

At 00:08 EDT, the archive contained 136 observations with no recorded errors.
The scoped queue contained 128 pending URLs, one in flight, and 21 excluded URLs.
Exclusion history recorded 26 missing associations (some subsequently resolved)
and 16 captured listings that did not meet the collection policy.

A new pre-request check reuses a saved canonical unit capture only when its
payload identifies the exact requested advertisement and contains full inline
history. It requires an unambiguous canonical-unit membership, a successful
latest observation in the same generation, its saved body, and eligible unit
identity. Old snapshots are interpreted offline without rewriting them. The
alias records the source observation, snapshot and body hash; no new observation
is fabricated. Historical mentions of a different advertisement do not qualify.

Offline replay verified six pending duplicate requests could be skipped; all six
were marked superseded in the live queue under its writer lock before restart. Eight
already completed advertisement routes also had reusable unit captures, indicating
prior duplication; those captures remain intact. Forty targeted tests passed.
The candidate lists are in `data/probes/west-village-20260920-review/`; its
database copy was deleted on September 22. The live deployment uses runtime-v5,
with unchanged two-per-minute pacing, one worker, no request cap and no deadline.

## September 20 01:09 EDT offline coverage audit

The consistent audit snapshot contains 258 captures with no recorded errors,
20 verified same-advertisement reuses, 72 pending scoped URLs, one in flight,
and 21 excluded scoped URLs. The crawl remains active at two submissions/minute.
No restart or extra paid requests were needed for this review.

Historical exclusion records must not be counted as permanently rejected units.
Of 29 captures previously marked ineligible, 11 now have a matching canonical
association, ten conflict with their associated canonical unit URL, and eight
lack a canonical unit page. The ten conflicts concern `564-hudson-street-new_york`:
source canonical URLs end in `3` or `3fl`, while the discovery association ends
in `03`. These identities remain distinct; no unit-label normalization or merge
was applied. Current association support alone does not replace analytical
validation or rewrite any archived eligibility interpretation.

A reusable read-only audit command now distinguishes the historical exclusion
trail from the latest interpretation. It retains observation IDs, body hashes,
source-declared canonical URLs and associated URLs, and uses a single SQLite
read transaction. Tests verify the audit does not change archive contents,
distinguishes resolved evidence from conflicts, and detects a later failed
capture. Ten audit/policy tests passed.

```sh
uv run --locked --no-sync python -m streeteasy_archive.collection_audit \
  --data /data1/apartments/archive/crawls/west-village-low-rate-20260919 \
  --output data/probes/west-village-audit-UNIQUE-TIMESTAMP.json
```

An existing output file is never overwritten. This review's report and identity
evidence are saved under `data/probes/west-village-20260920-0109/`; its database
snapshot was deleted on September 22. The new command does not change the
running frozen scraper and makes no provider requests.

## September 21 completion and September 22 yield review

The v5 run finished its eligible queue at 21:58 EDT on September 21
(`finish_reason: finished`); it was not stopped by credits or blocking. Scoped
frontier: 4,136 done, 18,610 excluded, 164 superseded, none pending. There were 43
transient provider failures (`Oxylabs response did not contain one result`)
recorded as coverage gaps. All 1,474 in-scope building pages and 1,310 expanded
rental inventories were captured.

A consistent copy is frozen read-only at
`/data1/apartments/archive/snapshots/west-village-backfill-20260921/archive.sqlite3`
(SHA-256 in the adjacent `.sha256` file). The granular transform is
`/data1/apartments/archive/datasets/west-village-granular-20260922-canonical-url-v1`.
The audit is `data/probes/west-village-20260922-final/audit.json`.

**The yield is thin: 231 canonical rental units (974 advertisement IDs), versus
about 22,000 fitted Chelsea units.** The unavailable-rentals inventories list
17,865 rows. Each row gives the latest advertisement's list date, unit label, price, beds,
baths and area. The rows form 17,791 distinct (building, label) pairs. All 20 known units
with an inventory row have exactly one, consistent with one row per unit.
Inventory rows link only to `/rental/<id>` advertisements, never to canonical unit
routes. Under the policy, those advertisements cannot be fetched until a unit page
vouches for them, so 17,861 were excluded as `missing_canonical_unit_association`.
The inventory evidence itself (2006–2026) is already archived and needs no
further requests.

### Inventory-label unit probes (`inventory-label-unit-probe-v1`)

Under `rental-canonical-v1`, a verified building's rental inventory now enrolls
`building/<slug>/<label lowercased, alphanumerics only>` as a unit-route request
target. A probe is only a guess. Membership still comes solely from the probed
page's own canonical URL and rental history, so a wrong guess costs one request
and authorizes nothing. On Chelsea's 25,314 source-declared (label, canonical URL)
pairs, this rule matches 93.0%. Misses are mostly zero-padding (`#7F` → `07f`) or
floor suffixes (`#2` → `2flr`); all 20 West Village overlaps match. Policy
`setup` replays archived inventories offline and idempotently. The claim order
puts unit routes ahead of advertisement routes, because one unit page carries the
unit's full price history.

An offline dry run on a scratch copy enrolls **17,229 unit probes** and adds no
observations. A successful probe re-queues that unit's historical advertisements,
about four per unit in the known sample. Scale: about 17.2k requests for unit
pages (≈6 days at two per minute), plus up to about 55k advertisement pages
(≈19 more days). Launching this new, larger paid queue needs explicit approval.

### September 22 relaunch (v6)

The user approved unit pages first, then historical advertisements until credits
run out. `apartments-west-village-low-rate-20260919-v6.service` was started at
16:50 EDT on the same archive via `data/probes/west-village-20260919/resume-v6.py`.
It uses the fixed `runtime-v6/src`: v5 plus the probe route, identical to the
tested working tree (3,230 tests passed). Controls are unchanged: one worker,
at most two submissions per minute, no cap or cutoff. It stops on account,
payment or credit rejection and on source blocking, with no automatic restart.
A 404 from a wrong label guess is recorded as a coverage gap, not a block. A
redirect enrolls its target. The Codex hourly heartbeat
`improve-west-village-scrape-efficiency` is still active but has hit its usage
limit on every run since September 20.

The first v6 start at 16:50 was OOM-killed under `MemoryMax=2G` during offline
policy setup, before any request. The cause was a `fetchall()` of every snapshot's
extraction, which is 4.8 GB on this archive. Setup now lists IDs first and loads one
extraction at a time. Measured on a scratch copy, the full startup peaks at 130 MB and
enrolls 17,229 probes in about 6.5 minutes. The service was relaunched with the
same controls.

First v6 results: the first 10 probes, all in 51 Leroy Street, returned HTTP 200. Each
was an eligible unit page whose declared canonical URL equals the probe URL.

## Handoff status (September 23, 07:55 EDT)

**The crawl is running at four submissions per minute.** On September 23 at 07:51
EDT the user doubled the rate. `apartments-west-village-low-rate-20260919-v6` was
stopped cleanly and relaunched with `resume-v6-4pm.py`, which differs from
`resume-v6.py` only in `--api-rps 1/15` (was `1/30`); the runtime source is
unchanged. Earlier, on September 22, it had been stopped twice by machine-wide
memory exhaustion (an OOM kill at 20:00 EDT and a reboot around 22:20 during
concurrent model fits in other sessions), not by provider or account errors. The
service is a transient `systemd-run` unit, so a reboot removes it and it must be
relaunched by hand after checking for account errors.

Progress since the v6 launch (observations after ID 4179), as of 07:51: 1,457
requests, 1,023 HTTP 200 unit pages, 433 HTTP 404 label misses and one transient
provider failure. Units with canonical membership grew from 223 to 1,139. Queue:
1,456 probes done, 15,772 pending and one in flight. The cascade has also re-queued
1,284 historical advertisement routes; unit routes are claimed first.

The 404 rate rose overnight (about 38% of requests after 22:29) because the misses
are concentrated in two large buildings whose inventory labels often do not match a
unit page: `the-archive` (297 of 590 probes) and `110-horatio-street-new_york` (114
of 256). Other buildings stayed near 3%. This is a coverage gap, not a block.

### Restart

Use this if the service is stopped (check the journal for HTTP 401/402/403 first).
The runtime is fixed and unchanged. Resume replays 2.5 to 6.5 minutes of offline setup
(peak about 130 MB), then continues at four submissions per minute:

```sh
systemctl --user reset-failed apartments-west-village-low-rate-20260919-v6
systemd-run --user --unit=apartments-west-village-low-rate-20260919-v6 \
  --description='West Village canonical rentals with inventory-label unit probes' \
  --property=WorkingDirectory=/home/ben/code/apartments --property=RuntimeMaxSec=infinity \
  --property=TimeoutStopSec=30 --property=Restart=no --property=MemoryMax=2G \
  /home/ben/code/apartments/.venv/bin/python -u \
  /home/ben/code/apartments/data/probes/west-village-20260919/resume-v6-4pm.py
```

Check the service, then the progress counts with a read-only SQLite
connection (`?mode=ro`):

```sh
systemctl --user is-active apartments-west-village-low-rate-20260919-v6
journalctl --user -u apartments-west-village-low-rate-20260919-v6 -n 30 --no-pager
```

Useful queries: `observations WHERE id>4179` grouped by status;
`count(DISTINCT unit_url) FROM collection_memberships`; and the frontier state of
URLs whose `scope_urls.reason` starts with `inventory-label`.

### Standing controls and cautions

- The user approved unit pages first, then historical advertisements, until Oxylabs
  credits run out. Keep one worker and at most four submissions per minute (raised
  from two on September 23 at the user's request), with no
  automatic restart. Do not restart after account, payment or credit rejection
  (HTTP 401/402/403), and do not buy credits. 404s are coverage gaps, not blocks.
- The runtime, `.venv` and `.env` live under the default checkout and are gitignored.
  Do not delete, rebuild or `uv sync` that `.venv`, and do not edit
  `data/probes/west-village-20260919/` while the crawl runs. Change code through a
  new fixed runtime directory (`runtime-v7`) and a controlled stop and resume.
- Memory: the service's cgroup sits at its 2 GB `MemoryMax` within minutes, but
  that is reclaimable file cache from reading the archive; the process itself uses
  under 100 MB (September 23: 61 MB anonymous, no cgroup OOM kills). An unprivileged user service cannot
  lower its own OOM priority. Before
  large fits run alongside the crawl, check free memory or coordinate with the
  fitting session.
- The Codex heartbeat `improve-west-village-scrape-efficiency` is paused.
- Scale: about 15.8k unit probes remain (about 2.7 days at four per minute), then
  historical advertisements (possibly about 55k).

### Code and version control

- jj bookmark `west-village-unit-probes` (on master): the scraper, tests and this
  document. `lineage-cache-page-speedup` is stacked on it. Workspace:
  `/home/ben/code/apartments-c5-wv`.
- The shared default working-copy commit (`a21d6e74`) still holds earlier
  uncommitted Codex modeling work plus copies of these files. Rebasing it onto
  `lineage-cache-page-speedup` is awaiting the user's decision.
- Open report from the Model Improvement session:
  `test_actual_accepted_current_cohort_and_joint_counterfactual` fails only after
  `tests/test_bayesian_floor_spline_readers.py` runs in the same process. The
  per-process lineage cache (`reviewed_lineage_cache._VERIFIED`) is the suspected
  state leak. This has not been investigated.

### After collection

Freeze a new read-only snapshot, run `models/transform_local.py` with a new run ID,
and run the collection audit. The September 22 frozen snapshot, dataset and audit are
listed above and must stay unchanged.

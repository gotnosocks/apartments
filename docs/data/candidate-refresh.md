# Bounded candidate refresh through Oxylabs

`apartments.candidate_refresh` refreshes an explicit set of previously observed
StreetEasy rental advertisements. It archives each response before interpreting
it, preserves both ACTIVE and inactive source statuses, and publishes a new
capture-time candidate snapshot. It never edits the source archive or discovers
additional URLs during the run.

For newly discovered advertisements, use the separate
[discovery detail collector](discovery-detail-refresh.md). It shares the durable
capture executor but verifies a search-review queue, preserves unfiltered product
scope, and resolves unknown unit identities from detail pages.

The project `.env` supplies `OXYLABS_USERNAME` (or `OXYLABS_USER`) and
`OXYLABS_PASSWORD`. It is ignored by Git. Credentials are read locally and
excluded from saved transport metadata and progress output. All collection uses
the existing Oxylabs transport; no direct StreetEasy HTTP fallback is used.

## Freeze the selection and check one response

```sh
uv run --locked python -m apartments.candidate_refresh \
  --snapshot data/exports/chelsea-candidates-20260918-asof1600 \
  --output data/probes/chelsea-candidate-refresh-20260918 \
  --max-targets 50 --max-new-requests 1
```

The input must be a verified canonical capture snapshot. Selection uses its
recorded knowledge cutoff, the latest capture within each advertisement, a
seven-day age limit by default, and the usual rental eligibility checks. It does
not apply a budget or willingness-to-pay filter. This selects previously observed
eligible advertisements; it does not establish that unselected units are absent
from the market. Stale earlier advertisements, known furnished/short-term/
concession listings and conflicting active advertisements are outside this pass.

Each target is the specific `/rental/<id>` advertisement URL, with its expected
canonical physical-unit URL. A unit landing page can change which advertisement
it presents, so it is not substituted for the requested advertisement.

The published `plan/refresh-plan.json` fixes the selection, source manifest,
correction ledger manifest, implementation hashes, and request limits. Source
code is copied into the plan bundle. Targets are never silently truncated: if
selection exceeds `--max-targets`, the command fails before collection. The
default limit is 50, with an allowed explicit maximum of 100.

Requests are sequential, at no more than one Oxylabs API submission per second.
The provider handler allows up to three submissions per target for retryable
failures. Thus the plan's submission ceiling is three times the target count;
this is a request bound, not a quoted dollar cost. Browser rendering is disabled.
`--max-new-requests 1` bounds the preflight to one target, potentially three API
submissions, and is not part of the immutable target plan.

## Resume and verify

Remove `--max-new-requests 1` to finish the same plan. Reusing the output directory
reuses completed captures and results; a genuinely new refresh uses a new output
directory. A changed source, correction manifest, implementation or target plan
cannot silently resume the old run.

- A durable request intent precedes each paid request. If an interrupted request
  has no saved response, its outcome is recorded as uncertain and not resubmitted
  automatically. The provider might have charged for that request.
- Raw bodies have content hashes and gzip storage; observations retain collection
  timestamps and redacted provider metadata, independently of parsing success.
- A saved response without a parsed checkpoint is interpreted without another
  request. Completed result checkpoints verify their associated body hashes.
- Authentication rejection, source challenges and source HTTP 401/403/429 stop
  the batch. That pause survives restarts, including an interruption between
  result publication and pause publication. Review the response before preparing
  any new collection; rerunning the same plan does not work around the pause.
- Advertisement and canonical unit identities must both match. A redirect to a
  different advertisement, a missing page or an ambiguous payload cannot restore
  the old ACTIVE claim. A failure is unknown availability, not proof of inactivity.

Current price/status parsing may succeed when only the historical event panel is
unavailable. Other ambiguous/failed parse states are rejected. The source warning
is retained, and current rent still comes from the current pricing payload,
never from a historical initial ask.

Corrections use the source snapshot's frozen knowledge cutoff, applied at the new
collection instant. Effective-time rules can therefore change which correction
applies. Capture IDs are namespaced to the refresh plan so an old capture-specific
correction cannot accidentally match the local observation number. Later review
edits require a new versioned projection.

## Outputs and scoring

`archive/` holds responses and transport observations. `results/` holds verified
per-target results. The completed `snapshot/` bundle contains:

- `candidates.jsonl`: every successfully interpreted fresh capture, including
  inactive advertisements;
- `failures.jsonl`: explicit failed or uncertain outcomes;
- `changes.jsonl`: status, price and attribute changes from the selected earlier
  capture, plus request/body provenance;
- `report.json`: counts, source statuses, failure reasons and scope limitations.

Feed only the fresh `snapshot/candidates.jsonl` into `score-apartments`, with an
`--as-of` after its latest knowledge timestamp and an explicit age limit. The
selector removes newly inactive or otherwise ineligible rows. Do not concatenate
failed targets' old ACTIVE records back into this input.

An ACTIVE payload is a source statement at capture, not guaranteed availability.
The result is a bounded refresh of earlier advertisements, not current Chelsea
coverage or discovery of newly listed apartments. See the
[scoring contract](../model/robust-candidate-scoring.md) for price-target,
preference and uncertainty limitations.

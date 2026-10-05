# Website thread handoff

What the next turn of the website thread needs. Updated at each milestone.

## State (2026-10-05 08:40 UTC)

- **Estimate form live.** `/estimate` uses the prediction kit (#228, `rentfrontier.kit`) through
  the site build (#229). The kit for the served u3 run is at
  `/data1/apartments/frontier/kits/<run>-05eecfc`, and build 20261005T083600015380Z-f33640aa
  passes both checks (scoring within 0.24% on 93 rows, encoding at least 99.7%).
- **Kit step for Modeling.** After the summary bundle and rent map, and before
  `apartments.site build`:
  `cd /data1/apartments/serve/master/frontier && JAX_PLATFORMS=cpu ops/job light -m 8G -- uv run --frozen --extra gpu python -m rentfrontier.kit <run> --summary <bundle>`.
  A build without the kit shows "not available for this build".
- **Validation page** shows the served design's unit split, marked indicative when the fit failed
  the gate (#232).

## Next

1. After the Oct 5 data publish (Modeling sends the build id), run
   `/data1/apartments/tmp/anatomy/postpublish.py`. Available now should show about 148 Chelsea
   and 87 West Village listings with capture dates.
2. Run playtest round 3 with six personas, including the landlord and the journalist. The landlord
   persona focuses on `/estimate`, and the round covers West Village current listings. The brief is
   `/data1/apartments/tmp/playtests/brief.md`, reports go in
   `/data1/apartments/tmp/playtests/<date>/`, and the venv is `/data1/apartments/venvs/playtest`.
3. Optional: cache the parsed kit per database (about 12 ms per request).

## Standing rules

Merge and deploy site PRs after subagent review. About-page attribution stays anonymous.
fields-review-v2 is held by Ben's choice.

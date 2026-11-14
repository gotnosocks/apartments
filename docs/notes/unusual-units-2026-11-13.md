# S14: penthouses, garden apartments and townhouse floors against L1's spread (2026-11-13)

S7 of the causal screens (`docs/notes/causal-screens-2026-11-13.md`) found that L1 prices
duplex ads right on average and misses their spread. Their clipped squared gap from L1's
median is 0.0114 against 0.0059 for the other held-out ads, and L1's 80% interval covers 0.719
of them. A multiplier on L1's noise scale and unit sd for duplex ads, picked on half of the
buildings, came out at 1.3 and 1.4 and gained 255 ± 30 elpd, and the same search on other ads
picked 1.0. D1 (`docs/notes/duplex-factor-2026-11-13.md`) puts that factor into the model.

In this screen I ask whether three other unusual kinds of apartment scatter wider in the same
way: a penthouse, a garden apartment and a floor of a townhouse or brownstone. It runs against
L1's saved fit, the pool `drift-building-phase-b0-latest-9a7830fb-l1`, and its dataset
`b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise`. Nothing is fit, and nothing goes to
Modal. The scripts are in `docs/notes/unusual-units-2026-11-13/` and write to
`/data1/apartments/tmp/sprint-20261113/unusual-units/`.

## Predictions, written before the readers and the scatter step ran

I wrote these after `u1_text.py` had matched the patterns and drawn the samples, and before
any reader returned or `u2_scatter.py` ran. At that point I knew only the share of listings
each pattern marks: 1.9% for a penthouse, 3.7% for a garden apartment and 4.2% for a
townhouse floor. L1 already has a penthouse label and a garden or ground label among its unit
columns, so it can price these kinds on average; the predictions are mostly about spread.

1. Precision against the readers is at least 0.85 for the penthouse pattern (70%), at least
   0.75 for the garden pattern (60%) and at least 0.75 for the townhouse pattern (55%).
2. Recall from the unmatched reads comes out over 0.6 for each pattern (50%), with an interval
   too wide to rule out 0.4 (80%).
3. Among held-out ads, S7's duplex pattern also marks 15% to 35% of the penthouse ads (65%),
   10% to 30% of the garden ads (60%) and 5% to 20% of the townhouse ads (60%). The townhouse
   pattern marks 15% to 40% of the garden ads (55%).
4. Each kind is within 1% of L1's median within building (75%), since L1 has the penthouse
   and garden labels among its columns and its unit level carries a unit's earlier asks.
5. Penthouse ads have a clipped squared gap 1.3 to 2.0 times that of the rest (65%), and L1's
   80% interval covers them 0.03 to 0.08 less often than the rest (60%). The multiplier comes
   out at 1.2 to 1.4 in both halves (55%), and its gain exceeds 2 SE (75%).
6. Garden ads have a squared gap 1.2 to 1.7 times that of the rest (60%), m of 1.1 to 1.3
   (60%), and a gain over 2 SE (65%).
7. Townhouse ads have a squared gap 1.1 to 1.5 times that of the rest (60%), m of 1.1 to 1.2
   (55%), and a gain over 2 SE (60%). Part of it comes from small buildings, whose ads scatter
   more in general: in S7's part C other ads in lots of 1 to 5 units had a squared gap of about
   0.008 against about 0.005 in lots of 100 or more.
8. Without the duplex ads, each kind keeps at least half of its excess squared gap over the
   rest (60%).
9. The null search on as many unmarked ads picks 1.0 in both halves and gains under 5 elpd for
   every kind (90%).
10. Adding a kind's ads to D1's duplex mark, with one multiplier for both, gains more than 2 SE
    over the duplex mark alone for the penthouse (60%), the garden apartment (50%) and the
    townhouse floor (45%), and under 150 elpd for each (80%).

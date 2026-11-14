# Outdoor size: the stated private outdoor area from ad text, screened against L1 (2026-11-14)

S16 (`blind-spots-2026-11-14.md`) found that ads stating an outdoor area of 300 sq ft or more,
by S7's match, ask +0.021 ± 0.005 over L1's median on the 684 held-out ads outside its draw,
with 1.42 times the spread and 71% inside L1's 80% interval. L1 reads the six private outdoor
types and the private-outdoor feature from the listing codes, and none of its columns gives
the size. If a bigger private terrace is worth more, part of that excess should follow the
size. To test this I wrote a tighter extractor, `rentfrontier.b0outdoorsize`, put its two
columns into a copy of L1's dataset, had readers check a sample of its matches and screened
the columns against L1's held-out predictions. Nothing is fit, nothing goes to Modal, and no
photo, floor plan or OxyLabs page is fetched. The scripts are in
`docs/notes/outdoor-size-2026-11-14/` and write to `/data1/apartments/tmp/outdoor-size-2026-11-14/`.

## Predictions, written before the precision reads and the screen

I wrote this section at 04:55 ET on 2026-11-14 and committed it before I drew the reads or
computed any gap for the new columns. At that point I knew:

- the extractor's results on the 460 reads I developed it on: S7's 400 reads, where it agrees
  with the readers' area within 5% on 94 of the 95 ads both give an area for, and S16's 60
  precision reads, where it marks all 26 `outdoor_large` ads the readers called private and
  none of the 4 they called shared or unclear;
- its counts over L1's 1,896,471 rows: 13,718 rows with an area, 12,058 of them with a
  private-outdoor code, and 1,475 held-out ads outside S16's draw, 1,338 coded and 137 not;
- S7's finding that among held-out ads with the private outdoor flag and a stated size, the
  gap doesn't rise with the size (-0.02 ± 0.16% per doubling), with every bin from 100 sq ft up
  at +1.8% to +2.5% and the ads under 100 sq ft at -0.1%;
- S16's figures for `outdoor_large`, given above.

What I expect:

1. **Precision.** The readers confirm the area on 0.90 or more of the pool, weighted by
   stratum, with the lower end of the 95% interval above 0.75. Leaving out unclear answers,
   0.93 or more.
2. **Level.** The 1,475 marked held-out ads ask +0.010 to +0.025 over L1's median on average.
3. **By size.** Ads under 100 sq ft come out between -0.010 and +0.010, ads from 100 to 300 sq
   ft between 0 and +0.020, and each bin from 300 sq ft up between +0.012 and +0.030.
4. **Slope.** Within the marked ads, the gap rises by -0.3% to +0.5% per doubling of the area,
   with an SE near 0.2%, so I expect no clear slope, as S7 found. Within the coded ads alone,
   the same.
5. **Spread and coverage.** The standardized residual's sd comes to 1.1 to 1.5 times that of
   all held-out ads in each bin, highest from 300 sq ft up. The share inside L1's 80% interval
   comes to 0.70 to 0.78 from 300 sq ft up and 0.74 to 0.80 below.
6. **Coded or not.** The 137 uncoded ads ask 0 to 3 points more over L1's median than the
   1,338 coded ones, since L1 has no outdoor column to give them. Their mean gap comes to
   +0.015 to +0.045, with an SE near 0.01.
7. **A model term.** I write one, without fitting it, if the slope is 0.5% per doubling or
   more and over 2 SE, or if the uncoded ads differ from the coded ones by more than 2 SE.
   Otherwise I write none, and the columns stay in the dataset copy for later screens.

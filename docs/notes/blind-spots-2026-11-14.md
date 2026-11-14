# S16: blind spots in L1's misses (2026-11-14)

Duplexes came to light because I read ads, not because a residual plot showed them: renters
price a second level, and L1 has no column for it. In this screen I look for more qualities of
that kind. I take L1's largest misses on its held-out ads, in both directions, with random
held-out ads as controls, and have Sonnet readers name a priced quality missing from the coded
fields, without showing them the ask or the group. When a cause turns up much more often among
the misses than among the controls, I count it as a candidate blind spot.

The screen runs against L1's saved fit, the pool `drift-building-phase-b0-latest-9a7830fb-l1`,
and its dataset `b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise`, on the latest split.
Nothing is fit, nothing goes to Modal, and no photo or OxyLabs page is fetched. The scripts are
in `docs/notes/blind-spots-2026-11-14/` and write to `/data1/apartments/tmp/blind-spots-2026-11-14/`.

## Predictions, written before the draw and before any ad was read

When I wrote these I had computed nothing on L1's held-out ads for this screen. I knew from
earlier notes that L1's noise is a Student-t with `nu` 1.69, so its tails are heavy and the
extreme misses are few standard scales out; that `furnished` and `short_term` are false on
every row of L1's dataset, so L1 can't tell a furnished ad from an empty one; that the
rewritten income flag adds 122 held-out ads to the old one's, at 0.107 under L1's median
(S15); that the rewritten shared flag marks 33 held-out ads (the text-flag screen); and that
duplex and text-penthouse ads scatter about 35% wider than others around L1's median (S7, S14).

The draw takes 150 overpriced and 150 underpriced misses and 100 controls. "Overpriced" means
the ad asks far above L1's median, and "underpriced" far below it.

1. **Data errors lead both miss groups.** The readers put 30% to 50% of the underpriced misses
   and 20% to 40% of the overpriced misses down to a data error in beds, baths, unit or price,
   against at most 8% of the controls (70%). Over all 300 misses the share is 25% to 45%, with
   my point guess at 33% (65%).
2. **Overpriced misses.**
   - Furnished or short-term is the most common unseen quality, in 10% to 25% of them, against
     at most 3% of the controls (60%).
   - A unit far larger than its count suggests, such as a whole house or a loft coded with few
     rooms, comes to 5% to 15% (55%).
   - Penthouse or top floor, private outdoor space, duplex and views each come to 2% to 8%
     (55%), and 10% to 25% taken together (55%).
3. **Underpriced misses.**
   - Shared or room rentals come to 8% to 20% (60%), and income-restricted or other program
     ads to 8% to 20% (60%).
   - With data errors, those two make up over half of the underpriced misses (60%).
   - Garden or basement units come to 2% to 8% (50%), and a unit needing work under 5% (60%).
4. **Controls.** "None apparent" is the most common answer among the controls, at 35% to 65%
   (65%). Renovation state is the most common named quality there, at 8% to 20% (55%), since
   readers will name a gut renovation whenever an ad boasts one.
5. **Direction.** For each of the three most common causes in a miss group, the readers' stated
   direction agrees with the group's sign in at least 70% of its reads (65%).
6. **The bar of step 4.** Between 5 and 9 causes pass it (65%), with my guess at 7: data
   error, furnished or short-term, shared or room rental, income-restricted, a unit far larger
   or smaller than its count, and one or two of penthouse, private outdoor space, duplex and a
   luxury building. At most 2 of the passing causes are new to the project's screens (60%).
7. **The cap.** Three ads a building per group displaces 15 to 60 ads from the two miss groups
   together, mostly from a few buildings of income-restricted or room-rental ads (60%), and
   none or almost none from the controls (90%).
8. **Missing text.** Ads with no description over 80 characters make up 5% to 15% of the
   misses against 2% to 6% of the controls (55%).
9. **Patterns.** Each flagged cause with a first text pattern reaches a precision of at least
   0.7 on its 30 read matches (55%).

## The draw

All times below are New York time on 2026-11-14.

I gave each of L1's 189,647 held-out ads a standardized residual,
z = (log ask - L1's median) / s, with s = (q75 - q25) / 1.349 taken from L1's predictive
sample in `pred_scores.npz` (`b1_draw.py`). The median s is 0.0625.

| Group | Ads | Buildings | z | Gap in log points |
|---|---|---|---|---|
| Overpriced: largest z | 150 | 132 | 6.06 to 19.15 | 0.21 to 1.36 |
| Underpriced: smallest z | 150 | 140 | -22.03 to -5.60 | -1.96 to -0.18 |
| Controls: random, seed 20261114 | 100 | 99 | -2.63 to 2.23 | -0.15 to 0.16 |

I took at most 3 ads from a building in each group. With that cap in place I skipped 2
overpriced ads, and no others. I froze the draw as `draw.parquet` (SHA-256 `fbac931fd294e2a9aa659f3beadad82cae50d1987db9809cddfd0df5a48ba541`, in
`draw.json`) before writing a single batch.

## The reading

For each drawn ad, `b2_fields.py` gathered the coded fields L1 reads, along with the size,
floor, building and code fields a renter would check, and the latest description from the
records file S7 used. It replaced dollar figures and monthly amounts with `[amount]`, 183
figures over the 400 texts, and cut each text at 3,500 characters. The mask let one figure
through: in read 34, an underpriced ad, the text keeps "$3500each", because the pattern needs
a word break after the digits. Its reader quoted that figure against the masked monthly pay
and labeled the ad net effective, lowering the ask. A search of the 20 batches for a dollar
sign before a digit finds no other. I shuffled the 400 ads together with seed 20261114 and
wrote 20 batches of 20. Readers got the rubric in
`reader_prompt.txt`, with nothing about the ask, L1's prediction or the group. Of the 400
ads, 357 have a description over 80 characters: 125 of the 150 overpriced, 138 of the 150
underpriced and 94 of the 100 controls.

I ran 20 Sonnet readers, one per batch, at most 8 at once, and launched each batch once:

- batches 00 to 07 started at 02:12 and finished by 02:15:36;
- batches 08 to 15 finished between 02:18:47 and 02:19:33;
- batches 16 to 19 finished between 02:20:58 and 02:21:18.

The Agent tool refused no reader, so I relaunched none. The reader of batch 16 reported 19
lines written, while its file holds 20, one for each ad of the batch. I counted from the
files. Over all 400 reads, the readers gave the direction "raises" 198 times, "lowers" 69
times and "unclear" 133 times.

## Categories, fixed before unblinding

I read each label's cause, note and evidence with only its read_id, and wrote the mapping
into `b3_harmonize.py`. That script never opens `key.parquet` or `draw.parquet`. It wrote
`labels.parquet` at 02:22:48 (SHA-256 `9c116e44e239cac9387410693f5ddc9e70fd92139bfb8ebc3e3cf3e1a97bea23`, in `harmonize.json`), and I started
`b4_score.py`, the first script to join a label to its group, at 02:23:26. The mapping:

1. The readers coined 18 causes, and I put each into a seeded category or a new one:
   - net-effective and free-rent readings into `net_effective`, along with 3 `data_error`
     reads whose note says the ask is net effective;
   - lofts, high ceilings and period details into `loft_ceilings_period`;
   - lease assignments and a resident-only studio into `tenancy_terms`;
   - a private elevator landing and an in-unit washer and dryer into `other_unit_feature`;
   - the rest into the seeded category each describes (blocked windows into
     `layout_fault`, a lobby-level unit into `garden_basement`, and so on).
2. I split `renovation` and `utilities_fees_included` by direction. Every renovation read
   says "raises", so the split leaves no needs-work subtype.
3. I gave each of the 56 `data_error` reads a subtype from its note: bedrooms too low (28),
   wrong unit or address (7), nonresidential space (7), bedrooms too high (4), baths (4), a
   wrong flag (3), a wrong size (2) and a whole house (1).

## Causes by group

Each share comes with an SE clustered by building (`b4_score.py`). Each difference is the
miss group's share less the controls', with a two-sample SE clustered by building. I set in
bold the differences of the causes and subtypes passing the bar of the next section. Bold
marks the bar alone, not significance: `private_outdoor` passes the bar at 1.5 SE.

| Cause | Overpriced | Underpriced | Controls | Over - controls | Under - controls |
|---|---|---|---|---|---|
| none_apparent | 39, .260 ± .039 | 46, .307 ± .039 | 34, .340 ± .047 | -.080 ± .060 | -.033 ± .061 |
| data_error | 35, .233 ± .037 | 17, .113 ± .026 | 4, .040 ± .020 | **+.193 ± .042** | **+.073 ± .031** |
| renovation | 15, .100 ± .025 | 15, .100 ± .026 | 21, .210 ± .041 | -.110 ± .048 | -.110 ± .048 |
| utilities_fees_included | 5, .033 ± .015 | 13, .087 ± .023 | 10, .100 ± .030 | -.067 ± .033 | -.013 ± .038 |
| duplex_multilevel | 10, .067 ± .021 | 9, .060 ± .020 | 6, .060 ± .024 | +.007 ± .031 | +.000 ± .031 |
| size_mismatch | 9, .060 ± .020 | 5, .033 ± .015 | 6, .060 ± .024 | +.000 ± .031 | -.027 ± .028 |
| private_outdoor | 11, .073 ± .023 | 5, .033 ± .015 | 3, .030 ± .017 | **+.043 ± .029** | +.003 ± .023 |
| net_effective | 6, .040 ± .019 | 9, .060 ± .019 | 4, .040 ± .019 | +.000 ± .027 | +.020 ± .027 |
| views | 7, .047 ± .017 | 5, .033 ± .015 | 3, .030 ± .017 | +.017 ± .024 | +.003 ± .023 |
| layout_fault | 0 | 6, .040 ± .016 | 5, .050 ± .022 | -.050 ± .022 | -.010 ± .027 |
| income_restricted_program | 0 | 9, .060 ± .019 | 0 | 0 | **+.060 ± .019** |
| penthouse_top_floor | 3, .020 ± .012 | 2, .013 ± .009 | 0 | +.020 ± .011 | +.013 ± .009 |
| loft_ceilings_period | 2 | 1 | 2 | -.007 ± .017 | -.013 ± .016 |
| furnished_short_term | 2 | 2 | 0 | +.013 ± .009 | +.013 ± .009 |
| garden_basement | 0 | 2 | 1 | -.010 ± .010 | +.003 ± .014 |
| luxury_building_missed | 2 | 0 | 1 | +.003 ± .014 | -.010 ± .010 |
| shared_room | 1 | 2 | 0 | +.007 ± .007 | +.013 ± .009 |
| tenancy_terms | 1 | 2 | 0 | +.007 ± .007 | +.013 ± .009 |
| other_unit_feature | 2 | 0 | 0 | +.013 ± .009 | 0 |

The data-error subtypes, as counts in each group:

| Subtype | Overpriced | Underpriced | Controls | Over - controls |
|---|---|---|---|---|
| bedrooms too low | 24 | 2 | 2 | **+.140 ± .037** |
| nonresidential space | 6 | 1 | 0 | **+.040 ± .016** |
| wrong unit or address | 3 | 3 | 1 | +.010 ± .015 |
| bedrooms too high | 1 | 3 | 0 | +.007 ± .007 |
| baths | 0 | 3 | 1 | -.010 ± .010 |
| wrong flag | 1 | 2 | 0 | +.007 ± .007 |
| wrong size | 0 | 2 | 0 | 0 |
| whole house | 0 | 1 | 0 | 0 |

The directions within a category:

- Every one of the 16 private-outdoor reads among the misses says "raises".
- All 9 income-program reads say "lowers".
- Net-effective reads say "lowers" in 14 of the 15 among the misses, including 5 of the 6 in
  the overpriced group, against that group's sign.
- Duplex reads say "raises" in every group, controls included, and duplexes turn up at the
  same rate in all three groups.
- Readers gave a renovation half as often in each miss group as among the controls, and
  every one of the 15 in the underpriced group says "raises". When an ad boasts a gut
  renovation the readers pick it, whatever the ask.

The readers were sure of themselves about as often in each group. Controls drew 16 high, 54
medium and 30 low confidence; overpriced ads drew 44, 70 and 36; underpriced ads drew 48, 59
and 43.

## Flagged causes

I flag a cause when a miss group has at least 5 reads of it and has it at least twice as often
as the controls, or has it while no control does. The bar comes from step 4 of the task brief
for this screen, which I had before I wrote the predictions. The predictions commit gives no
number for it, so prediction 6 refers to the brief's bar. I put the bar into `b4_score.py` after the
predictions commit and before unblinding at 02:23:26. The brief asks for at least 5 misses,
and I count those 5 within a single miss group. Three categories pass:

1. `data_error`, in both groups: 5.8 times the controls' share among overpriced ads and 2.8
   times among underpriced ads. Two subtypes pass on their own, both in the overpriced
   group:
   - bedrooms too low: 24 reads against 2 among the controls. In 20 of the 24 the ad is coded
     as a studio. The listing's codes give 11 of those 20 a unit of 5 to 8 rooms, such as a
     "5 room duplex" with 0 bedrooms, and 5 of them a single room, as on the sprint's blank
     forms;
   - nonresidential space: 6 reads and no control, for storefronts, retail space, a nail
     salon, a yoga studio and offices.

   The underpriced group's 17 data errors spread over 8 subtypes, none with 5 reads.
2. `private_outdoor`, among overpriced ads: 11 reads against 3, 2.4 times as often, though
   the difference is only 1.5 SE. In several of the 11 the listing already codes a terrace
   and the text gives it 516 to 1,800 square feet.
3. `income_restricted_program`, among underpriced ads: 9 reads and none elsewhere, citing
   HPD lotteries, AMI bands and 421-a.

Penthouse or top floor, furnished or short-term, shared rooms, tenancy terms and other unit
features also turn up in no control, but none has 5 reads in a miss group.

## Patterns, their counts and their precision

For each flagged cause I wrote a field or text pattern in `b5_patterns.py` and matched it
against the latest description of each listing in L1's dataset:

- `studio_rooms`: coded 0 bedrooms, with 4 to 20 rooms in the listing's codes;
- `studio_text_beds`: coded 0 bedrooms, with a description giving 1 to 6 bedrooms ("2 bed",
  "three bedrooms", "1BR") or 4 to 9 rooms;
- `nonresidential`: a description with "storefront", "retail space", "commercial unit", "key
  money", "medical office", "community facility", "nail salon", "restaurant space" or the
  like, and without the phrase "ground floor retail";
- `outdoor_uncoded`: a description giving a private, own or exclusive terrace, balcony,
  patio, garden, yard, roof deck or outdoor space, or a wraparound terrace, on a listing with
  no private-outdoor code;
- `outdoor_large`: a stated outdoor area of 300 square feet or more, from S7's match;
- `income_v2_new`: the rewritten `income_restricted_v2` of #1378 on a row without L1's
  `income_restricted`;
- `income_v2_all`: the whole `income_restricted_v2`, counted for scale beside `income_v2_new`.

For the precision reads I drew 30 matches of each of the first five patterns, with seed
20261114, from matches with a description over 80 characters. I masked the dollar figures as
before and gave each reader the bedrooms, full baths, coded room count and whether the
listing codes any private outdoor space, with a yes, no or unclear question about the
advertised unit (`precision_prompt.txt`). The five Sonnet readers ran at once, each launched
once, and none was refused. I left the income patterns unread: #1378 read the new-only
matches and found 60 of 60 true, for a precision of 0.986 (0.930 to 0.997) over the whole
flag.

| Pattern | Rows | Training | Held-out | Units | Buildings | Precision, all 30 | Precision, settled | Flagged reads matched |
|---|---|---|---|---|---|---|---|---|
| studio_rooms | 2,873 | 2,602 | 271 | 2,516 | 1,529 | 4 of 30, .13 (.05 to .30) | 4 of 19, .21 | 12 of 24 bedrooms too low |
| studio_text_beds | 38,728 | 34,816 | 3,912 | 25,556 | 5,239 | 2 of 30, .07 (.02 to .21) | 2 of 20, .10 | 15 of 24, and 5 controls |
| nonresidential | 3,462 | 3,123 | 339 | 2,490 | 748 | 1 of 30, .03 (.01 to .17) | 1 of 29, .03 | 5 of 6 overpriced |
| outdoor_uncoded | 38,733 | 35,326 | 3,407 | 31,061 | 11,251 | 17 of 30, .57 (.39 to .73) | 17 of 21, .81 | 3 of 11 overpriced |
| outdoor_large | 6,681 | 5,993 | 688 | 4,701 | 2,657 | 26 of 30, .87 (.70 to .95) | 26 of 28, .93 | 3 of 11 overpriced |
| income_v2_new | 1,166 | 1,045 | 121 | 973 | 274 | not read here | .986 in #1378 | 8 of 9 |
| income_v2_all | 2,698 | 2,433 | 265 | 2,241 | 506 | not read here | .986 in #1378 | 8 of 9 |

The "all 30" precision counts an unclear answer as a miss, and the "settled" precision leaves
unclear answers out. Both come with 95% Wilson intervals (`b7_precision.py`). The units are
building and unit_id, or the row alone when unit_id is empty. The whole income flag's counts
agree with I1's note (`income-noise-2026-11-14.md`).

S15 gave 122 held-out ads to the new-only part, at -0.107. Since S15b the `-textflags` copy
holds the flag with its negation guard, which unmarks 5 new-only rows. One of them is a
held-out ad at +0.049, so 121 remain, at -0.109. I checked this against S15's unguarded flags
in `/data1/apartments/tmp/text-flags-2026-11-13/t3_flags.parquet`.

On the held-out ads, "gap" means the log ask less L1's median, with its mean and a
building-clustered SE. "Spread" is the median absolute deviation of the gap, over that of all
held-out ads. "In 80%" gives the share inside L1's 80% interval. I drew the 400 read ads by
their gap and wrote the patterns after reading them, so the held-out figures would otherwise
count the very misses that suggested each pattern. I leave all 400 drawn ads out of them, the
100 controls along with the 300 misses, and give the figures with the 400 in beside. Over the
189,247 other held-out ads the spread is 0.0404, the share in 80% is 0.798 and the mean gap
is -0.005. With the drawn ads in, the 189,647 give 0.0405, 0.797 and -0.004.

| Pattern | Ads, drawn out | Gap | Spread | In 80% | Drawn ads | Gap, drawn in | Spread, drawn in | In 80%, drawn in |
|---|---|---|---|---|---|---|---|---|
| studio_rooms | 258 | +.038 ± .010 | 1.55 | .64 | 13 | +.068 ± .014 | 1.64 | .61 |
| studio_text_beds | 3,891 | +.001 ± .002 | 0.91 | .79 | 21 | +.004 ± .002 | 0.92 | .79 |
| nonresidential | 334 | -.004 ± .008 | 1.14 | .76 | 5 | +.008 ± .010 | 1.14 | .75 |
| outdoor_uncoded | 3,398 | +.005 ± .002 | 1.04 | .78 | 9 | +.006 ± .002 | 1.05 | .78 |
| outdoor_large | 684 | +.021 ± .005 | 1.42 | .71 | 4 | +.024 ± .005 | 1.42 | .71 |
| income_v2_new | 113 | -.064 ± .016 | 1.33 | .62 | 8 | -.109 ± .028 | 1.55 | .58 |
| income_v2_all | 251 | -.039 ± .010 | 1.77 | .59 | 14 | -.063 ± .015 | 1.87 | .56 |

Without the drawn ads, the gap of `studio_rooms` drops from +0.068 to +0.038, both income
patterns move about 40% toward zero, and `nonresidential` goes from +0.008 to -0.004. The
other patterns move by 0.003 or less.

Each failure has a plain reason in the readers' answers:

- `studio_rooms`: most matches are studios, alcove studios and junior one-bedrooms coded with
  4 or 5 rooms, which must count a foyer, a kitchen or an alcove. Of the 2,873 matches, 2,457
  have 4 or 5 rooms, so the 30 drawn do too, while 11 of the 12 overpriced reads it catches
  have 5 to 8. After the precision reads I split the matches by coded room count
  (`b6_studio_rooms.py`). The split is post hoc: I chose it after the reads showed me where
  the bedrooms-too-low ads fall, and no precision read covers it. As above, the main figures
  leave out the drawn ads:

  | Coded rooms | Rows | Ads, drawn out | Gap | In 80% | Drawn ads | Gap, drawn in | In 80%, drawn in | Bedrooms-too-low reads |
  |---|---|---|---|---|---|---|---|---|
  | 4 | 1,968 | 188 | +.020 ± .008 | .69 | 1 | +.022 ± .009 | .69 | 1 |
  | 5 | 489 | 42 | +.086 ± .035 | .48 | 6 | +.153 ± .045 | .42 | 6 |
  | 6 | 214 | 14 | +.138 ± .064 | .43 | 1 | +.182 ± .076 | .40 | 1 |
  | 7 | 53 | 1 | +.658 | 0 of 1 | 3 | +.669 ± .080 | .00 | 3 |
  | 8 to 20 | 149 | 13 | -.021 ± .036 | .69 | 2 | +.096 ± .085 | .60 | 1 |
  | 5 to 20 | 905 | 70 | +.085 ± .027 | .50 | 12 | +.173 ± .037 | .43 | 11 |

  At 5 rooms or more, the 70 held-out ads outside the draw ask +0.085 ± 0.027 over L1's
  median, and half of them fall inside its 80% interval. The 12 drawn ads among the 82 are
  all overpriced misses, 11 read as bedrooms too low and 1 as nonresidential, at gaps of +0.51
  to +0.90. Without them a single ad remains at 7 rooms, and the bin of 8 to 20 rooms drops
  from +0.096 to -0.021 ± 0.036. Of the 8 precision reads at 5 rooms, 1 found a one-bedroom, 3
  a studio and 4 couldn't tell.
- `studio_text_beds`: the bedrooms in the text belong to other units, to a size ("the size of
  a 1 bedroom") or to a convertible studio. The drift note's second round of cautions found
  the same thing, at 10 of 80.
- `nonresidential`: the words come from building copy in apartment ads. The readers found 28
  of the 30 to be apartments, and the 5 overpriced reads it catches make a sliver of its 3,462
  matches.
- `outdoor_uncoded`: 4 of the 30 have shared space only, and 9 don't say whose space it is.
- `outdoor_large` holds up. Of its 30 reads, 25 already carry a private-outdoor code, so the
  stated size adds to a type L1 reads. It catches only 3 of the 11 overpriced outdoor reads,
  since S7's match misses many of the ways an ad states a size.

## Overlap with L1 and with other work

- **Room count.** L1 reads the room count only through `ad:extra_rooms`, the rooms less the
  bedrooms less 1, clipped to 0 to 6. A studio coded with 5 rooms gets an `extra_rooms` of 4,
  and still the 70 held-out ads at 5 rooms or more outside the draw ask +0.085 ± 0.027 over
  L1's median, or +0.173 with the 12 drawn ads in. I split by room count after the reads, so
  these figures are post hoc. These ads
  differ from the outlier sprint's blank forms, which the feed codes as 0 bedrooms, 1 bath
  and 1 room: here a lister typed a room count of 5 or more and left the bedroom count at 0.
  The sprint used the room count to pick out blank forms and to back its corrections, and I
  found no screen there of studio-coded ads with 5 rooms or more.
- **Nonresidential space.** L1 has no column for it. The outlier sprint screened commercial
  spaces and rooms: the ledger excludes the clear cases its readers found, the other matches
  showed gaps near zero, and no pipeline rule came of it. `analysis.building_check` drops
  ads on nonresidential lots with no apartments, which leaves storefronts in mixed-use
  buildings.
- **Private outdoor space.** L1 reads the six outdoor types and the private-outdoor feature,
  carried over a unit's earlier ads as a share. It doesn't read the size. S7's match gives
  the size, and a private outdoor size from a Haiku extraction was scoped on 2026-11-12
  (`unit-flags-scope-2026-11-12`). The TODO item for text columns lists private outdoor space
  on rows with an empty field at +0.0154, where I find +0.005 ± 0.002 on the narrower
  `outdoor_uncoded`, with the drawn ads left out.
- **Income programs.** L1 reads the old `income_restricted`. The rewritten flag (#1378)
  matches 8 of the 9 income reads, and I1 takes it to a fit.
- **Net effective.** L1 reads the coded months free, and #1379 adds months free from the
  text. The category didn't pass the bar.
- **Duplexes and penthouses (D1).** Duplexes come to 6.7%, 6.0% and 6.0% of the three groups
  and penthouses to 3, 2 and 0 reads. Under a Student-t with `nu` 1.69, a factor of 1.35 on
  the noise scale, inside the 1.3 to 1.4 S14 picked for duplexes, would put duplexes into
  extreme misses about 1.7 times as often as into controls. With these counts I can't tell
  1.7 from 1.0.
- **Gardens and townhouses (S14).** Garden or basement units come to 0, 2 and 1 reads, and
  no reader gave a townhouse floor.
- **Furnished and short-term.** Both flags are false on every row of L1's dataset, yet the
  readers gave furnished or short-term ads only 2 overpriced and 2 underpriced reads.

## The predictions scored

1. **Missed.** Data errors come to 23.3% of the overpriced misses (20% to 40% predicted) and
   4.0% of the controls (at most 8%), both inside. They come to only 11.3% of the
   underpriced misses (30% to 50%) and 17.3% of all misses (25% to 45%, guess 33%).
2. **Partly hit.** Furnished or short-term comes to 1.3% of the overpriced misses against my
   10% to 25%, a miss. Size comes to 6.0% (5% to 15%). Penthouse 2.0%, outdoor 7.3%, duplex
   6.7% and views 4.7% each fall in 2% to 8%, and 20.7% together falls in 10% to 25%.
3. **Missed.** Shared rooms come to 1.3% and income programs to 6.0% (8% to 20% each); with
   data errors they make 18.7% (over half predicted); garden or basement units come to 1.3%
   (2% to 8%). A unit needing work comes to 0% (under 5%), the one part inside.
4. **Missed narrowly.** "None apparent" comes to 34% of the controls, under the 35% to 65% I
   gave. Renovation is the most common named quality there, at 21%, over the 8% to 20% I gave.
5. **Missed.** Among overpriced misses, data errors agree with the group's sign in 71% of
   reads, renovation in 100% and private outdoor in 100%. Among underpriced misses, data
   errors agree in 65%, renovation in 0% and utilities or fees in 31%.
6. **Missed on the count, hit on novelty.** The bar is the one in the task brief's step 4,
   which the prediction cites without restating: at least 5 reads in a miss group, at twice
   the controls' share or with no control at all. I wrote it into `b4_score.py` after the
   predictions commit and before unblinding. Three categories pass against my 5 to 9, and none
   is new to the project: data errors run through the outlier sprint, the income flag is
   #1378's and the outdoor size was scoped on 2026-11-12. Both passing subtypes have earlier
   work too, in the sprint's studio-coded ads and its commercial screen. The room count as a
   clue to a studio-coded apartment is the one new angle.
7. **Missed for the misses, hit for the controls.** The cap displaced 2 miss ads against my 15
   to 60, and no control.
8. **Hit.** Ads with no description over 80 characters come to 37 of the 300 misses (12.3%:
   16.7% of the overpriced and 8.0% of the underpriced) and 6 of the 100 controls (6.0%, at
   the top of my range).
9. **Missed.** Only `outdoor_large` passes 0.7, at 0.87. `outdoor_uncoded` comes to 0.57 and
   the bedroom and nonresidential patterns to 0.03 to 0.13.

Most misses carry no cause a reader could find in the text: "none apparent" comes to 26% and
31% of the miss groups against 34% of the controls, and the named causes other than data
errors, outdoor space and income programs turn up about as often in misses as in controls.

## Follow-ups, ranked

I judge level and scatter from the direction mix within each cause, together with the
held-out gap and spread of its pattern. The held-out figures below leave out the 400 drawn
ads, and after each gap I give the gap with the drawn ads in.

1. **Income programs, with `income_restricted_v2` in place of `income_restricted`.** The
   whole flag marks 2,698 rows: 2,433 training rows and 265 held-out ads, as in I1's note.
   The 251 held-out ads outside the draw ask -0.039 ± 0.010 against L1's median (-0.063 with
   the drawn ads), with 1.77 times the spread and 59% inside L1's 80% interval. The ads the
   new flag marks and the old one doesn't come to 1,166 rows and 121 held-out ads in 274
   buildings. The 113 of those outside the draw ask -0.064 ± 0.016 (-0.109 with the drawn
   ads), with 1.33 times the spread and 62% inside the 80% interval. Precision 0.986 (#1378),
   and the flag catches 8 of the 9 income reads. All 9 reads lower the ask, so it is a level
   shift with some scatter besides. The flag exists and I1 fits it.
2. **Stated outdoor size.** All 16 outdoor reads among the misses raise the ask. The pattern
   marks 6,681 rows and 688 held-out ads. The 684 outside the draw ask +0.021 ± 0.005 (+0.024
   with the drawn ads), with 1.42 times the spread and 71% inside the 80% interval, so a
   level with wider scatter. Precision 0.87, but S7's match catches 3 of the 11 outdoor
   reads. The Haiku extraction scoped on 2026-11-12 would need to catch more of them.
3. **Studios coded on units of 5 or more rooms.** I chose this split after the reads, so it
   is post hoc, and no precision read covers it. The reads point to a level shift: 22 of the
   24 overpriced bedrooms-too-low reads raise the ask and the other 2 are unclear. The split
   marks 905 rows and 82 held-out ads. The 70 outside the draw ask +0.085 ± 0.027 over L1's
   median, with half inside the 80% interval: +0.086 on 42 ads at 5 rooms, +0.138 on 14 at
   6, a single ad at 7 and -0.021 on 13 at 8 to 20. With the 12 drawn ads in, the 82 ask
   +0.173. I rank it below the outdoor size because its level rests on 70 ads and a split I
   picked after seeing the reads, and the precision reads at 5 rooms found 1 one-bedroom in 8.
   Before any rule, read 30 of the 905 against the unit's other ads and its floor plan count.
   The rule may need the unit's history, as the sprint's rule B2 does.
4. **Private outdoor space without a code.** 38,733 rows and 3,407 held-out ads. The 3,398
   outside the draw ask +0.005 ± 0.002 (+0.006 with the drawn ads), a small level with no
   extra spread, at a precision of
   0.57 (0.81 among settled reads). It belongs with the text-columns item in `docs/TODO.md`.
5. **Nonresidential space.** It comes to 4% of the overpriced misses and no control, but the
   readers gave a direction in only 2 of its 7 reads, so I can't call it a level or a
   scatter. The text pattern fails at 1 in 30, its 334 held-out ads outside the draw ask
   -0.004 ± 0.008 (+0.008 with the drawn ads), and the sprint's commercial screen found its
   matches near zero gap. A rule would need the ad's headline or the listing's property
   type, with a read of its matches first.

Net-effective ads lower the ask in 14 of 15 miss reads but split across both groups, at 1.0
and 1.5 times the controls' share, and #1379 already covers them.

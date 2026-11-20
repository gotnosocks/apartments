# Why 96 building levels did not mix: a read of their ads (2026-11-20)

No fit and no money spent. This follows `docs/notes/kept-rhat-audit-2026-11-20.md`, which found
that 51 buildings on the live run and 72 on the backtest had a kept level (`kept/bld`) with
split R-hat over 1.05, and that none has a live Deals ad on the run where it is flagged. That
note proposed a read of those buildings for the ledger. This is the read.

Runs: the live run `drift-building-bedtext-layout-range-b0-market-6cd1f12b-range-m3` and the
backtest `drift-building-bedtext-layout-range-b0-market-d9028c57-range-j`. The union is 96
buildings, 27 of them flagged on both. For each, every training ad was tabulated and its
whole text read, with the ask set against the median ask of the same neighbourhood, year and
bedrooms. The classes below are my reading of those texts; they are not coded from fields.
Files: `docs/notes/building-level-read-2026-11-20/` (scripts `s0.py` to `s11.py`, which read
parquet files in `/data1/apartments/tmp/po-bldmodes/` that are not committed; `make_tables.py`
and `check_quotes.py`; and the tables named below). The ad texts themselves are not committed.

## The drafted ledger rows are candidates

`building-level-read-2026-11-20/candidate_rows.ndjson` holds 68 drafted rows in the form of
`pipeline/ledger/*.ndjson`, with quotes prefixed `Ad text: `. They are not in the ledger. Each
still needs `decided`, `source` and `when` from whoever imports them, and the quotes are
checked against the stored texts by `check_quotes.py` (0 of the quotes missing). Merging a rule
version makes the served fit unservable until a refit, so the rows wait for Ben's word and the
next refit; none is imported here, and no quarantine or rule file is touched.

A row is a candidate only when the ad as a whole shows that the product or the ask is wrong; ad
text never overrides a coded field. The first draft had 75 rows. After review, the whole text
of every one of the 75 was read again against its coded fields, and each was decided on the
whole ad:

| outcome | rows | which |
|---|---|---|
| read | 75 | all |
| kept as drafted | 64 | |
| re-kinded | 4 | 3795761, 3362161, 4729603 to location_conflict; 4013887 to product_scope |
| dropped | 7 | 4626114, 2335984, 2609225, 1639122, 1244901, 1545128, 1715063 |
| in the file now | 68 | 64 kept and 4 re-kinded |

Why the 7 were dropped: 2609225 calls itself a studio, so a 0 bed code does not conflict with
the text; 2335984 says 1 bedroom, which matches the code; 1244901 has only a bare
"month-to-month", too weak for a short-term reading; 4626114 (drafted as a malformed ask),
1639122 (a location conflict) and 1545128 and 1715063 (nonresidential) were not supported by
the whole ad. Why the 4 were re-kinded: 3795761 is a live-work loft on
Mercer Street in Soho joined to a Brooklyn building, so the kind is a location conflict and not
a Brooklyn apartment in Manhattan; 3362161 and 4729603 were filed as `brooklyn_misjoin` but the
ads place them in Manhattan under a Brooklyn building, which is the reverse and is
`location_conflict`; 4013887 is one ask for a retail unit and an apartment, which is product
scope and not a plain nonresidential ad. The 68 by reason: nonresidential 37, bedrooms_unknown
11, location_conflict 10, product_scope 5, and one each of malformed_ask (3937379), price_basis
(3429110), tenfold_ask_unbacked (2072139), attribute_conflict (2514821) and
explicit_short_term_offer. The 11 `bedrooms_unknown` rows are ads coded 0 bed with an empty or
one-character text where the same building shows ads of the unit or its neighbours as larger;
for 384 St Johns the building's other ads of July and August 2024 (4485730, 4494087) are 3 beds
at $4,875, though their unit ids differ, so that they are the same unit is not verified.

What the rows change on scored ads, counted from the tables. None of the drafted rows is
a scored ad: none of the 68 is a live Deals ad and none is a held-out ad of
the backtest. One live ad sits in a flagged building (the flag is on the backtest run only
for that building): 5163798 at 86 Cornelia Street. Row 2514821 (a 2018 ad coded 0 bed at
$3,400 whose text says 4 bed) is one of that building's 4 training ads in the live dataset
too, but the live run's level for 86 Cornelia is 0.02 with R-hat 1.00, so the drafted row does
not move that ad in any way I can show. Three held-out ads of the backtest sit in flagged
buildings: 4875635 (22 E 18th), 4899902 (16 Goodwin, already in the ledger) and one at 360 S
1st (flagged on the live run only). None of the 68 rows lies in 22 E 18th, 16 Goodwin or
360 S 1st, so the drafted rows reach none of the three backtest ads. The first read said "0
live ads and 3 backtest ads changed"; the tables support "0 and 0" for the drafted rows.

## Counts by class

One primary class each, 96 in all:

| class | buildings | what it is |
|---|---|---|
| commercial ad coded as an apartment | 36 | stores, offices, a restaurant, warehouses, a lease |
| placeholder ad | 19 | Brooklyn units with empty or one-character text, beside real ads |
| wrong ask or wrong beds | 8 | annual as monthly (2), tenfold (1), $2,200 townhouse (1), 4 others |
| two buildings under one id | 9 | ads whose text names another street or neighbourhood |
| a real difference in the building | 8 | senior living (21 Clark), hotel and short-stay operators |
| model shape, data correct | 11 | studio beside a triplex; lofts beside a penthouse; 2 over 1.05 |
| unclear | 5 | 142 E 65th, 428 Columbus, 123 E 86th, 321 Troutman, 43 W 11th |

So 72 of the 96 (the first, second, third and fourth rows) are data errors that a ledger row
can remove, 8 are real but outside the product (short stay, assisted living), and 11 are the
model's shape. 56 of the 96 have a single training ad on a flagged run, so the two modes are
"this one row is ordinary" against "this one row asks several times the area". The class of
each building is in `classes.csv`.

The 37 nonresidential candidate rows, in 31 buildings, ask a median 6.8 times the area median
(quartiles 3.8 and 10.0, range 0.4 to 21.5). 34 are coded 0 bed and 3 are 1 bed.
The placeholder class has 87 training rows in its 19 buildings (47 coded 0 bed, 14 coded 1 bed, 26
coded 2 to 4 bed), asking $2,595 to $12,000 by my rule for a placeholder (text of 5 characters or
fewer, or "Draft", "Desc", "TBD"). The Nov 12 ledger entries removed the 0 bed placeholder rows of
several of these from the live run's data (10 Marconi, 1042 Herkimer, 22 Revere, 246 Vernon, 350
Knickerbocker, 1209 Union), which is why those are flagged on the backtest only: the backtest
dataset was built under an older ledger.

## The ten worst

By the larger of the two R-hats. Training ads are those on the live and backtest datasets.

| building | class | R-hat live, back | level live, back | ads live, back |
|---|---|---|---|---|
| 43 W 46th | commercial | 1.00, 14.05 | 2.17, 1.08 | 3, 3 |
| 138 7th Ave, Brooklyn | commercial | 1.00, 10.88 | 1.37, 0.69 | 5, 5 |
| 21 Clark St | real difference | 9.60, 9.74 | 0.62, 0.61 | 6, 6 |
| 10 Marconi Pl | placeholder | 1.00, 6.41 | 0.07, 0.56 | 6, 10 |
| 113 W 69th | model shape | 6.03, 1.00 | 0.22, -0.11 | 14, 13 |
| 142 Duane | model shape | 5.59, 1.00 | 0.40, 0.06 | 9, 9 |
| 147 11th St, Brooklyn | commercial | 1.78, 5.02 | 0.48, 0.72 | 1, 1 |
| 384 St Johns Pl | placeholder | 1.00, 4.59 | 0.56, 0.29 | 10, 10 |
| 198 W 9th, Brooklyn | placeholder | 1.98, 4.25 | 0.26, 0.34 | 5, 5 |
| 1042 Herkimer | placeholder | 1.01, 3.76 | -0.01, 0.32 | 8, 5 |

What each is, from the ads (rows in `ten_worst_rows.csv`, with only a 40-character text start):

- 43 W 46th: an office at $1,800 and two ads for a restaurant at $22,000, 8.3 times the area.
  Both chains settle high on the live run (2.17) with R-hat 1.00; on the backtest they split.
- 138 7th Ave: three ads for a store or office on 7th Avenue in Park Slope at $8,500 to $9,000
  (3.4 to 5.0 times the area), then two real apartments at 1.0 and 0.6 times the area.
- 21 Clark: studios at $2,050 and $2,200 in 2014, then four 2021 ads of a senior living
  conversion (assisted and independent living) at $11,095 to $18,320.
- 10 Marconi: placeholder ads of one or two letters coded 0 bed at $5,000 beside real 2, 3 and
  4 bed ads of the same units at $3,750 to $4,999.
- 113 W 69th and 142 Duane: real ads. A brownstone with ground-floor studios and an owner's
  triplex, and lofts beside a penthouse of over 7,200 sq ft at $39,000 to $40,000. One level
  cannot serve both, so the chains disagree about which to favour.
- 147 11th St: one ad, 7,500 sq ft of commercial space at $28,000, 11.7 times the area.
- 384 St Johns, 198 W 9th, 1042 Herkimer: placeholder texts of a few characters. At 384 St
  Johns the six empty-text ads are coded 0 bed ($4,495 to $5,200); another ad of the building
  in the same months is a 3 bed at $4,875, and whether it is the same unit is not verified
  (the unit ids differ).

## The high side: which direction makes a false deal

A falsely high level raises the predicted rent, so an ordinary ask gets a low `below_share` and
climbs the Deals order. That is the direction that makes a false deal. A falsely low level only
hides a deal.

On the live run, 29 Deals ads in 18 buildings have a posterior mean level over 0.5, and every
one has R-hat under 1.02 (`high_level_deals_ads.csv`). So these are not the unmixed ones. They
were checked for the same mode as the 43 W 46th case: a level held high by a few odd rows.

| building | training ads | median ask over area median |
|---|---|---|
| one57 | 92 | 3.91 |
| 15 Central Park West | 95 | 3.06 |
| Central Park Tower | 36 | 4.03 |
| The Delecor | 86 | 2.90 |
| 222 W 80th | 158 | 2.44 |
| The Lucida | 163 | 2.43 |
| 25 and 80 Columbus Circle | 152 | 2.48 |
| 1085 Park | 39 | 3.71 |
| The Duchess | 49 | 2.48 |
| Waldorf Astoria Residences | 26 | 2.97 |
| The Langdon | 25 | 2.87 |
| The Gianna | 24 | 2.30 |
| 9 E 82nd | 18 | 2.91 |
| 131 E 70th | 7 | 1.87 to 5.81 |
| 350 E 84th | 8 | 1.48 to 3.04 |
| 11 Essex | 4 (all 2026) | 2.44 to 3.37 |
| Bouwerie Lane (54 Bond) | 4 | 1.0 to 2.6 |
| 102 Thames, Brooklyn | 475 | 1.21 (not read) |

The first thirteen rest on 18 to 163 ads that all sit far above the area, as luxury towers
do, so the level is the building and not a stray row. 102 Thames is the largest, at a modest
ratio; I did not read it. The four thin ones were read: 131 E 70th is a mansion of full-floor
units with a keyed elevator, 54 Bond is three full-floor lofts, 11 Essex is a new boutique
building (four 2026 rows for the same two or three units), and 350 E 84th is a 20 ft townhouse
of duplexes whose level a 4 bed whole-house row at $29,000 lifts. None is a same-mode error of
the 43 W 46th kind. 350 E 84th also has one 2014 row (1414051) that belongs to another building
and pulls its level down, not up.

Where the ads sit in the Deals order (6,502 ads, 4,896 without a caution; rank in the whole
order, in brackets among uncautioned ads; rank without the level is from the published interval
with the level taken out):

| ad | building | level | training ads | rank | rank without level |
|---|---|---|---|---|---|
| 5153934 | 350 E 84th (townhouse) | 0.62 | 8 | 107 (59) | 6,452 |
| 5204630 | The Delecor 2A | 0.52 | 86 | 156 (84) | 6,503 |
| 5178646 | 1085 Park 8A | 0.60 | 39 | 209 (116) | 6,503 |
| 5158580 | 15 CPW S802 | 0.87 | 95 | 280 (cautioned) | 6,503 |
| 5205319 | 131 E 70th 3EW | 0.76 | 7 | 349 (207) | 6,503 |
| 5138831 | one57 45C | 0.67 | 92 | 382 (225) | 6,503 |
| 5192635 | 222 W 80th 05B | 0.53 | 158 | 423 (255) | 6,503 |

4 of the 29 are in the first 300 of the whole order and 6 in the first 300 uncautioned (the table
shows the seven that rank under 450 of the 29). Each of the seven falls to the bottom of the order
with the level taken out, so its place rests wholly on the level. For the ads in large buildings
the level is as well founded as a level can be. For 350 E 84th the ask of $11,950 is an ordinary
one for the same duplex ($11,500 to $12,000 in 2023), and the model median of $15,606 is lifted by
the whole-house row.

Thin buildings under the 0.5 line matter more. 16 Deals ads sit in buildings with a level over
0.3 and five or fewer training ads, 2 of them in the first 300 (`thin_high_level_deals_ads.csv`;
with eight or fewer: 20 ads, 3 in the first 300, at ranks 44, 107 and 285):

- 5192010, 115 E 62nd (level 0.46, 4 training ads), rank 44 (22 uncautioned), ask $22,000
  against a model median of $35,005; rank 2,709 without the level. All four training rows are
  the whole townhouse coded 5 bed ($17,500 to $32,000). The live ad is the same house coded 3
  bed. The level means "whole house", so the model prices a 3 bed in such a building by it. The
  ask is a real cut from July's $32,000, but the $35,005 median is not a fair comparison.
- 5202428, 14 Spencer Place (level 0.36, 4 training ads), rank 285 (165). Three of the training
  rows are this autumn's placeholder ads (a period, "Draft", a one-line welcome) for 2 bed
  units at $8,899 to $9,495, and one is a 1 bed at $4,499. The live ad is a 2 bed cut to
  $8,499. The level rests on the unit's own earlier asks, so the "deal" is a price cut on an ask
  that never let.

In the first 300 of the whole order, 13 ads have a building level over 0.3 and 28 over 0.2.

Same-mode cases that R-hat cannot see do exist, in buildings with no live ad today. On the live
run both chains settled high for 43 W 46th (level 2.17), 70 Hester (1.69), 138 7th Ave (1.37),
322 E 57th (0.71), 384 St Johns (0.56) and 922 Lincoln (0.56). Five have live R-hat under 1.03;
922 Lincoln is 1.052. A new ad in any of them would be priced far too high and go to the top of
Deals. On the backtest, 86 MacDougal (level 0.98 on 2 training ads) and 430 Broome (0.53 on 1)
have held-out ads.

## The low side

A falsely low level lowers the predicted rent, so a good ask looks ordinary: it hides a deal and
does not make a false one. On the live run no building with a level under -0.5 has a live ad.
Under -0.3 there are 6 ads in 6 buildings, none in the first 300, all with many training ads:
1320-1328 Fulton (-0.38, 132 training ads, rank 1,487), 405 W 23rd (-0.30, 67, 1,565), 52 W 14th
(-0.33, 93, 1,807), 71 Thompson (-0.36, 92, 2,565), 150 Baxter (-0.30, 21, 4,183) and 181
Thompson (-0.42, 37, 6,090). On the backtest, The 74 (-0.73, 12 training ads) has 2 held-out
ads and 293 Hooper (-0.43, 2) has some. Among the 96, the low cases are single wrong rows: 334 E
69th (-0.72, the $2,200 townhouse), 226 W 11th (-0.45, a Columbia ad joined to the wrong
building), 43 W 11th (-0.37), 321 Troutman (-0.37) and 140 Metropolitan (-0.28, workspace).

## Next steps

1. Ledger rows. The first read counted 99 (43 nonresidential, 28 placeholders, 8 wrong asks or
   attributes, 14 misjoins, 6 product-scope or short-term). Four were already in the ledger
   (1443898, 1481485, 4886558, 4899902), which leaves 95, and 985 Jefferson's 4505676 ("Huge
   Studio in Bed Stuy", a real studio) was wrongly a placeholder, which leaves 94: 41
   nonresidential, 25 placeholders (11 coded 0 bed and 14 coded 1 bed), 8, 14 misjoins (9
   certain, 5 to re-read) and 6. The re-read above then dropped 7 of the drafted rows and
   re-kinded 4, so what stands is 68 drafted rows, plus 14 placeholder rows coded 1 bed, which
   need a rule decision because the field is filled and a coded field is not overridden by
   text (for example "ad text under ten characters and the same unit advertised with more
   bedrooms within a year"), plus 5 misjoin rows that need a re-read: 87 in all. The 41
   nonresidential of the first count is 37 drafted now (the draft file had 40: two dropped, one
   moved to product scope); the one-row gap between 41 and 40 I did not trace. The gate gain
   is that up to 72 of the 96 flagged levels go away (an upper bound; the dropped rows'
   buildings may stay flagged), and that no future ad joins a building with a level of 1 to 2.
   This waits for a rule version, which needs a refit to serve.
2. A publish-time caution for a high level on few training ads (over 0.3 on five or fewer, or
   eight or fewer). It must be tested on history before it reaches Deals: both of the two ads
   it catches in the first 300 are weak deals on reading, but that is two ads.
3. A post-fit list that does not rely on R-hat: buildings with a level beyond 0.5 in size and
   under ten training ads, with their rows. Six buildings with the same mode
   sat at levels of 0.56 to 2.17 on the live run: five at R-hat under 1.03 and 922 Lincoln at
   1.052.
4. A history sweep for commercial and placeholder ads: 0 or 1 bed, ask over three times the area
   median, text with "retail", "storefront", "office", "per sf" or "warehouse", and texts of a
   few characters. The 37 nonresidential rows found here are only those that happened to break
   R-hat; single rows that converged high are not in this list. This is the larger data job.
5. No model change for the Deals order now. The 11 model-shape buildings (a ground-floor studio
   beside an owner's triplex) would need a within-building size or whole-house term; none has a
   live ad. The 115 E 62nd case suggests a whole-townhouse feature is worth an expert read.

## Not verified

The class of each building is a manual read and was not re-coded from fields. Two statements
of the first read could not be checked and are left out: that 131 E 70th's floor asked $15,000
as a 2 bed in 2024 (its 2024 row has a different text), and a placeholder range for rows coded
0 or 1 bed of "$3,500 to $12,000" (the rows I can count run $2,595 to $12,000). 102 Thames was
not read.

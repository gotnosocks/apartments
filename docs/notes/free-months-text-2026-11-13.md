# Free months read from ad text (2026-11-13)

The pipeline codes `months_free` on 161,046 of L1's 1,896,471 rows. It is above zero on
160,941 of them, and on just 1,323 rows from before 2020. Ads from those years stated their
free months in the description alone. I wrote `rentfrontier.b0freetext` to read the offer in
each listing's latest description, and built a copy of L1's dataset with the reading in three
new columns. The module leaves `months_free` as it is and writes the text's reading beside it.
No fit reads the new columns yet, and I propose none here.

The scripts behind the numbers below are in `docs/notes/free-months-text-2026-11-13/`:

- `extract.py` writes each listing's latest description, where it mentions free rent, to a
  scratch file;
- `compare.py` prints the gains, the agreement with `months_free`, the counts by year and the
  price basis, and with `--samples` draws the ads for the readers;
- `score.py` scores the readers' labels.

## The build

    python -m rentfrontier.b0freetext SRC OUT

The script checks the records file of SRC's pipeline build against the SHA-256 in SRC's
manifest before reading it. For each listing it keeps the latest record, by the later of
`collected_at` and `last_collected_at`, as `b0duplex` does, and parses the description in
`raw_listing_json`. It writes

- `months_free_text`, the free months stated in the text, as a float, or 0 when the text denies
  any concession;
- `free_lease_months`, the lease length of the chosen offer, when the text gives one;
- `free_text_kind`, one of exact, up_to, conditional, none and unstated, or null when the text
  mentions no free rent.

It copies SRC's other files, refuses an OUT already on disk and leaves SRC unchanged. The
manifest's `free_text` entry records the source and its rows' SHA-256, the records file and its
SHA-256, the rule, the rates for weeks and days, and the counts.

I ran it in a `systemd-run --user --scope -q -p MemoryMax=3G` scope from L1's dataset

    /data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise

into the same path with `-freetext` at the end. It took 8 min 14 s, with a peak resident size of
1.52 GB, and read a record for every one of the 1,896,471 listings.

| rows | count |
|---|---|
| exact | 125,123 |
| up_to | 3,549 |
| conditional | 3,270 |
| none (0 months) | 79 |
| unstated (no count) | 30,947 |
| no mention of free rent | 1,733,503 |
| with months above 0 | 131,942 |
| with a lease length | 71,678 |
| with several offers | 7,988 |

## How I read an offer

In each description I look for a count of months, weeks or days beside a word for free (free,
rent free, on us, waived, complimentary, concession, abatement).

- I read counts in digits or in words. Halves come as 1.5, ".50", "1 1/2", "one and a half",
  "a month and a half" or "a 1/2 month", and I keep other decimals as written (2.66).
- I convert weeks at 52/12 to the month and days at 365/12, unrounded. The manifest records
  both rates.
- A month given by its place in the lease counts as one ("first month free", "13th month
  free"). A pair counts as two ("first and last month", "13th and 14th month free"), and "FIRST
  TWO MONTHS OF LEASE AND LAST MONTH ARE FREE" counts as three.
- "13 months for the price of 12" gives 1. A whole count of 7 or more months with free gives
  the place of the free month, so "12 MONTH FREE on a 12 month lease" gives 1.
- I take the lease length from the offer's own clause, or else from the next lease length
  later in its sentence.
- I pass over free parking, gyms, storage, cleaning and Wi-Fi, along with tax abatements and
  "broker fee free".

I set the kind from the offer's clause:

- up_to after "up to" or for a range like "1-2 months free", keeping its upper end;
- conditional when the clause sets a deadline or a qualification, or limits the offer to select
  units;
- exact otherwise;
- none, with 0 months, when the text denies a concession ("no concessions", "no free months")
  and makes no offer;
- unstated, with no months, when the text calls the price net effective, or mentions free
  rent without a count.

An offer described as left out of the price ("not reflected in the price", "gross rent listed
does not include 2 months free") still counts. In those ads the listed price is gross.

On 7,988 rows the description makes several offers, often one per lease length. I keep one,
taking in turn

1. an offer tied by the text to the listed price ("net effective rent advertised based on 1 month
   free", "advertised rent is with 8 weeks free"), unless its sentence says the price leaves it
   out;
2. an exact offer;
3. a conditional offer;
4. an up_to offer;

and among offers of the same rank, the first in the text. If the chosen offer has no lease
length, I give it the lease of another offer with the same count.

## Gains on L1's latest split

L1's latest split holds out 189,647 ads, one row and one listing each.

| `months_free` | text | rows | units | held-out ads |
|---|---|---|---|---|
| empty | months above 0 | 112,160 | 89,808 | 4,410 |
| empty | none (0 months) | 76 | 73 | 4 |
| zero | months above 0 | 2 | 2 | 0 |
| zero | none (0 months) | 0 | 0 | 0 |

The coded field is zero on only 105 rows, so the zero-coded split adds almost nothing. Of the
112,160 empty-coded rows with months, 108,070 are exact, 2,515 conditional and 1,575 up_to.
Counting coded rows as well, 3.73% of the held-out ads have months in their text.

## Against the coded field

On 19,783 rows the coded field is above zero and the text gives a value. The two agree within
0.1 month on 92.57% of them:

- 93.4% of the 17,051 exact readings;
- 87.7% of the 755 conditional readings;
- 87.0% of the 1,974 up_to readings;
- none of the 3 rows where the text denies a concession.

On the 1,469 rows in disagreement, the text's value is higher on 616 and lower on 853. On
141,158 coded rows the text gives no count. For 138,494 of them the latest description makes no
mention of free rent, and for 2,664 it mentions free rent with no count.

The cross-tab rounds both values to 0.01, and "other" collects the values outside the columns
shown:

| coded \ text | other | 0 | 0.46 | 0.5 | 1 | 1.5 | 2 | 2.5 | 3 | 4 |
|---|---|---|---|---|---|---|---|---|---|---|
| other | 277 | 0 | 5 | 30 | 36 | 1 | 38 | 23 | 47 | 2 |
| 0.5 | 2 | 0 | 213 | 750 | 41 | 0 | 6 | 0 | 1 | 0 |
| 1 | 65 | 3 | 26 | 29 | 8,536 | 34 | 155 | 1 | 21 | 2 |
| 1.5 | 102 | 0 | 2 | 5 | 49 | 709 | 61 | 0 | 5 | 1 |
| 2 | 70 | 0 | 3 | 2 | 202 | 29 | 4,810 | 35 | 90 | 0 |
| 2.5 | 2 | 0 | 2 | 1 | 2 | 4 | 21 | 582 | 40 | 0 |
| 3 | 31 | 0 | 0 | 0 | 45 | 9 | 39 | 9 | 2,069 | 16 |
| 4 | 9 | 0 | 0 | 0 | 1 | 0 | 36 | 0 | 9 | 337 |

- **Weeks.** At 52/12, two weeks free reads as 0.46, and the coded field gives 0.5 on 213 such
  rows. Of the 494 week offers on both sides, the coded value equals the weeks over 4 on 403
  and the 52/12 reading on 241, since the two rates differ by less than 0.1 for small counts.
  The ads compute their own net prices at 4 weeks to the month as well: "8 WEEKS FREE! G 2900 N
  2416" nets 2900 by 2 of 12 months, and "12 Weeks Free G 2600 N 2166" nets 2600 by 3 of 18.
  In the reader sample the coded field rounds 6, 5 and 3 weeks each to 1 month.
- **Another lease's offer.** Many ads offer one count on a shorter lease and another on a longer
  one, and the coded field can follow a different offer from my chosen one ("1 MONTH FREE ON
  13 MONTH LEASE, 2 MONTHS FREE ON 19"). Coded 2 against text 1 (202 rows) and coded 1 against
  text 2 (155) are mostly of this kind. On 332 of the 692 disagreeing rows with a lease in the
  text, the coded `lease_term` differs from the text's lease.
- **Up to.** The column keeps the upper end of "up to" offers and ranges. In the reader sample
  the coded value lies below that end on 4 of 6 such ads.
- **Coded values absent from the text.** Coded values such as 2.31, 1.11 and 1.13 appear in no
  offer of their ads and look derived from prices. One ad (listing 4811052) states months at
  odds with its own gross and net prices.

## The readers

I drew 350 ads from the first build with seed 20261113 and gave them to Sonnet subagents in 14
batches of 25. The readers had the description alone, without the parser's value or the coded
one. For each ad they returned the free months, the lease, the kind, every offer in the text
and the price basis.

After scoring the first build (v1) against the labels, I fixed the parser's misses found in the
labels and rebuilt (v2):

- "a 1/2 month", ".50 free month" and decimals beyond a half such as 2.66;
- ordinal pairs such as "13th and 14th month free";
- "abatement" as a word for free;
- the offer tied to the listed price, chosen ahead of the others.

The v2 scores come from the ads behind these fixes, so v1's scores are the better guide to new
text.

| sample | measure | v1 | v2 |
|---|---|---|---|
| found: 200 ads with a value and no coded one | readers read a rent offer above 0 | 199 | 199 |
| | value within 0.1 of the readers' | 197 | 199 |
| | kind equal to the readers' | 192 | 192 |
| | lease equal, of 108 stated by both | 104 | 106 |
| missed: 100 ads with no count and free, concession or net effective in the text | readers give a count | 2 | 2 |
| | the parser gives that count | 0 | 1 |
| disagree: 50 ads where the text and coded values differ by over 0.1 | readers agree with the text | 44 | 49 |
| | readers agree with the coded value | 5 | 5 |
| | readers agree with neither | 1 | 1 |

Precision on the found sample is 199 of 200. The ad outside it, listing 3069291, offers a
month free in the building and says "Incentives Do Not Apply" for the unit, and the reader
reports no offer. Of the parser's exact readings, the readers call 6 conditional and 1 none.

In the missed sample the readers give a count on two ads. Listing 1508825 runs words together
("ENVOY1 MONTH FREE") and v2 still misses it. Listing 3233614 offers "1 month abatement", which
v2 reads. The missed population holds 136,188 rows. For v1, 2 in 100 puts the share with a missed
count between 0.2% and 7% at 95%, and for v2, 1 in 100 puts it between 0.03% and 5.4%. The readers mark 19 of the 100 unstated, against 17 for the
parser.

In the disagree sample all 5 ads where the readers sided with the coded value were parser
errors, and v2 matches the coded value on them. On the other 45 the readers side with the text
on 44 and call the last unstated (listing 2865689). The coded value is one of the text's offers
on 13 of the 50, and 11 of the 50 are week offers, with the coded value at the weeks over 4 on
6.

## By year

| year | rows | text months > 0 | coded > 0 | text months, coded empty | unstated | up_to |
|---|---|---|---|---|---|---|
| 2013 | 3,144 | 110 | 0 | 110 | 19 | 0 |
| 2014 | 94,523 | 3,956 | 4 | 3,956 | 747 | 3 |
| 2015 | 112,331 | 6,053 | 5 | 6,053 | 838 | 25 |
| 2016 | 121,636 | 12,199 | 7 | 12,199 | 2,702 | 346 |
| 2017 | 146,357 | 20,198 | 18 | 20,194 | 5,371 | 104 |
| 2018 | 169,044 | 23,201 | 335 | 23,083 | 6,475 | 110 |
| 2019 | 155,795 | 19,814 | 954 | 19,456 | 5,695 | 182 |
| 2020 | 212,113 | 30,208 | 29,773 | 24,381 | 6,837 | 889 |
| 2021 | 193,715 | 5,981 | 51,682 | 1,226 | 1,839 | 979 |
| 2022 | 129,566 | 1,359 | 11,009 | 355 | 133 | 6 |
| 2023 | 144,785 | 2,399 | 17,031 | 312 | 123 | 106 |
| 2024 | 148,460 | 2,451 | 18,166 | 432 | 66 | 203 |
| 2025 | 145,685 | 2,688 | 19,077 | 202 | 60 | 386 |
| 2026 | 119,305 | 1,325 | 12,880 | 201 | 39 | 210 |

The 12 rows from 2011 and 2012 have no count. Before 2020 the text holds nearly every record
of concessions, with months on 85,051 rows lacking a coded value. From 2021 on the coded field
covers most offers, and the text adds a few hundred rows a year. One month is the commonest
value in every year and two months the next. Half months rise from 107 rows in 2022 to 222 in
2026. Unstated rows peak at 6,837 in 2020 and fall to 39 in 2026.

## The target is net of free months

The task behind this note took L1's target for a gross ask, to be netted with the text's
months. The target is net already wherever the field is coded, and most text-only ads state a
net price.

- `docs/model/drift.md` gives `y` as the log of the final asking rent, net of any free months
  (line 157), and lists "Asks are net of free months, and price histories are gross" among its
  known issues (line 449).
- On 99.27% of the 160,936 coded rows with a page price and a lease term, `latest_ask` equals
  `page_price * (1 - months_free / lease_term)` within $2. The pipeline nets these rows.
- On 97.36% of the 112,160 text-only rows, `latest_ask` equals `page_price` within $2. The
  pipeline leaves these rows as listed, and the listed price is mostly net. Of the 111,159 such
  descriptions in the extract, 74,926 call the price net effective and say nothing of a gross
  price, 710 say the listed price is gross or leaves the offer out, 377 say both, and 35,146
  say neither. (The extract keeps descriptions with free, concession or net effective, so it
  lacks the abatement-only offers.)
- The readers marked the basis net on 129 of the 200 found ads, gross on 12 and unstated on 59.

Netting the text-only asks by `months_free_text` would count the concession twice on most of
them. Gross asks enter L1's target only from the text-only rows stating a gross price, about 1%
of those with a stated basis by pattern and 9% by the readers.

## Uses

Before 2020 the column gives 85,051 rows a count of free months, where the coded field has
almost none. A fit could take the share of ads offering free months in a row's building or
neighborhood over the months before its price day as a measure of how soft the market was,
with the window ending at the price day as in `b0turnover`. The unstated and none kinds mark
30,947 asks called net effective without a count and 79 asks with a concession denied, and a
fit could test whether either group prices apart from the rest. The Deals page could show the
free months and the gross rent beside a net ask, so a renter can tell a low net ask from a low
rent. For the text-only rows with a gross price, the column gives the months to net the ask as the
pipeline nets coded rows, though a basis column has to come first to tell those rows
from the net ones.

## Left open

- The column converts weeks at 52/12, as the task asked, while the coded field and the ads'
  own net prices count 4 weeks to the month. A rebuild at 4 changes one constant.
- Words run together ("ENVOY1 MONTH FREE") go unread.
- An ad offering the building's concession and excluding its unit ("Incentives Do Not Apply")
  gets the building's offer.
- The column reads the listing's latest record alone. An earlier record of the same listing
  may state a different offer.
- No column yet marks the price basis (net or gross) of the text-only rows.

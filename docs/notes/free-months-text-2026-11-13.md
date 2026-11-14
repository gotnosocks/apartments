# Free months read from ad text (2026-11-13)

The pipeline codes `months_free` on 161,046 of L1's 1,896,471 rows. It is above zero on
160,941 of them, and on just 1,323 rows from before 2020. Ads from those years stated their
free months in the description alone. I wrote `rentfrontier.b0freetext` to read the offer in
each listing's latest description, along with any word there on whether the listed price is
net or gross, and built a copy of L1's dataset with these readings in four new columns. The
build leaves `months_free` and `latest_ask` as they are and writes the text's readings beside
them. No fit reads the new columns yet, and I propose none here.

The scripts behind the numbers below are in `docs/notes/free-months-text-2026-11-13/`:

- `extract.py` writes each listing's latest description, where it mentions free rent, to a
  scratch file;
- `compare.py` prints the gains, the agreement with `months_free`, the counts by year and by
  price basis, and the ads leaving their unit out of the building's offer. With `--samples` it
  draws the ads for the first reading, and with `--check` the ads for the second;
- `score.py` scores the readers' labels against the current parse;
- `records.py` looks for the coded value of each disagreeing row in all of its listing's
  records;
- `edges.py` counts the parser's known misreadings among the texts with months;
- `amounts.py` compares the page price of text-only rows with the net and gross amounts in
  their text.

## The build

    python -m rentfrontier.b0freetext SRC OUT

The script checks the records file of SRC's pipeline build against the SHA-256 in SRC's
manifest before reading it. For each listing it keeps the latest record, by the later of
`collected_at` and `last_collected_at`, as `b0duplex` does, and parses the description in
`raw_listing_json`. It writes

- `months_free_text`, the free months stated in the text, as a float, or 0 when the text denies
  any concession or leaves the unit out of the building's;
- `free_lease_months`, the lease length of the chosen offer, when the text gives one;
- `free_text_kind`, one of exact, up_to, conditional, none and unstated, or null when the text
  mentions no free rent;
- `ask_basis_text`, net or gross as the text describes the listed price, or null when it says
  neither or both.

It copies SRC's other files, refuses an OUT already on disk and leaves SRC unchanged. The
manifest's `free_text` entry records the source and its rows' SHA-256, the records file and its
SHA-256, the rules, the rates for weeks and days, and the counts by kind and by basis.

I ran it in a `systemd-run --user --scope -q -p MemoryMax=3G` scope from L1's dataset

    /data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise

into the same path with `-freetext` at the end. It took 12 min 37 s, with a peak resident size of
1.59 GB, and read a record for every one of the 1,896,471 listings.

| rows | count |
|---|---|
| exact | 125,122 |
| up_to | 3,549 |
| conditional | 3,270 |
| none (0 months) | 85 |
| unstated (no count) | 30,947 |
| no mention of free rent | 1,733,498 |
| with months above 0 | 131,941 |
| with a lease length | 71,689 |
| with offers of different counts | 7,894 |
| `ask_basis_text` net | 120,556 |
| `ask_basis_text` gross | 1,721 |
| text calling the price both, left null | 166 |

## How I read an offer

In each description I look for a count of months, weeks or days beside a word for free (free,
rent free, on us, waived, complimentary, concession, abatement).

- I read counts in digits or in words. Halves come as 1.5, ".50", "1 1/2", "one and a half",
  "a month and a half" or "a 1/2 month", and I keep other decimals as written (2.66).
- I convert weeks at 4 to the month, since the coded field counts them so and the ads compute
  their own net prices the same way: "8 WEEKS FREE! G 2900 N 2416" nets 2900 by 2 of 12
  months, and "12 Weeks Free G 2600 N 2166" nets 2600 by 3 of 18. The column fills in for
  `months_free` where that is empty, so I count in the coded field's units. I convert days at
  365/12, and leave both unrounded. The manifest records both rates.
- A month given by its place in the lease counts as one ("first month free", "13th month
  free"). A pair counts as two ("first and last month", "13th and 14th month free"), and "FIRST
  TWO MONTHS OF LEASE AND LAST MONTH ARE FREE" counts as three.
- "13 months for the price of 12" gives 1. A whole count of 7 or more months with free gives
  the place of the free month, so "12 MONTH FREE on a 12 month lease" gives 1.
- I take the lease length from the offer's own clause: the first lease length after the offer
  and before the next offer, or else the nearest one before it and after the previous offer.
  A lease in another sentence goes unread, so "1 month free. 12 month lease" gets no lease.
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

When the text says the building's concession leaves its unit out ("Incentives Do Not Apply.",
"Unit 3K is excluded from all promotions/concessions", "This apartment is not eligible for the
concession"), I give it none with 0 months, whatever the building offers. A line such as
"Concessions will not apply to renewals" limits the offer to new leases, and I keep the offer.
An offer described as left out of the price ("not reflected in the price", "gross rent listed
does not include 2 months free") still counts. In those ads the listed price is gross.

On 7,894 rows the description makes offers of different counts, often one per lease length. I
keep one, taking in turn

1. an offer tied by the text to the listed price ("net effective rent advertised based on 1 month
   free", "advertised rent is with 8 weeks free"), unless its sentence says the price leaves it
   out;
2. an exact offer;
3. a conditional offer;
4. an up_to offer;

and among offers of the same rank, the first in the text. If the chosen offer has no lease
length, I give it the lease of another offer with the same count.

## Net or gross listed prices

I read `ask_basis_text` from every row's text, coded or not:

- net when the text calls the price net effective ("net effective rent", "net rent", "NER") or
  ties an offer to the price ("rent reflects a month free");
- gross when the text calls the listed price gross ("gross rent advertised", "prices listed are
  the gross"), says the price is not net effective, or says the price leaves a concession out
  ("1 month free, not reflected in the price", "pricing listed does not include the free
  rent");
- null when the text says neither, or says both.

I pass over a net effective mention right after "not", "no" or "never", as in "approvals are
based on the gross rent, not the net effective rent". For "not included in the rent" I also
look for a concession word earlier in the sentence, so "utilities not included in the rent"
gives no basis. The text says both on 166 rows, which I leave null.

I left out a stated gross amount ("Gross Rent $3,200"). The extract has 45,021 texts with one,
39,760 of them on rows already marked net, and 10,563 with the amount after "based on", as in
"net effective based on a gross rent of $3,200". An amount like this gives the gross rent
without saying whether the listed price equals it. Settling that by comparing the amount with
the listed price would put the rent into a feature, against `docs/leak-free-scoring.md`.

| `months_free` | text months | net | gross | unstated or both | rows |
|---|---|---|---|---|---|
| above 0 | any | 9,583 | 74 | 151,284 | 160,941 |
| 0 | any | 1 | 0 | 104 | 105 |
| empty | above 0 (text only) | 82,720 | 917 | 28,522 | 112,159 |
| empty | none | 28,252 | 730 | 1,594,284 | 1,623,266 |
| all | | 120,556 | 1,721 | 1,774,194 | 1,896,471 |

On the held-out ads of L1's latest split:

| `months_free` | text months | net | gross | unstated or both | ads |
|---|---|---|---|---|---|
| above 0 | any | 1,032 | 9 | 17,377 | 18,418 |
| 0 | any | 0 | 0 | 10 | 10 |
| empty | above 0 (text only) | 3,178 | 22 | 1,210 | 4,410 |
| empty | none | 906 | 47 | 165,856 | 166,809 |
| all | | 5,116 | 78 | 184,453 | 189,647 |

So 28,522 of the 112,159 text-only rows have no basis in their text. By kind, the text-only
rows split as

- exact: 80,648 net, 843 gross, 26,578 unstated;
- conditional: 1,731 net, 27 gross, 757 unstated;
- up_to: 341 net, 47 gross, 1,187 unstated.

## Gains on L1's latest split

L1's latest split holds out 189,647 ads, one row and one listing each.

| `months_free` | text | rows | units | held-out ads |
|---|---|---|---|---|
| empty | months above 0 | 112,159 | 89,807 | 4,410 |
| empty | none (0 months) | 82 | 77 | 5 |
| zero | months above 0 | 2 | 2 | 0 |
| zero | none (0 months) | 0 | 0 | 0 |

The coded field is zero on only 105 rows, so the zero-coded split adds almost nothing. Of the
112,159 empty-coded rows with months, 108,069 are exact, 2,515 conditional and 1,575 up_to.
Counting coded rows as well, 3.73% of the held-out ads have months in their text.

## Against the coded field

On 19,783 rows the coded field is above zero and the text gives a value. The two agree within
0.1 month on 93.42% of them:

- 94.3% of the 17,051 exact readings;
- 89.1% of the 755 conditional readings;
- 87.6% of the 1,974 up_to readings;
- none of the 3 rows where the text denies a concession.

On the 1,302 rows in disagreement, the text's value is higher on 617 and lower on 685. On
141,158 coded rows the text gives no count. For 138,494 of them the latest description makes no
mention of free rent, and for 2,664 it mentions free rent with no count.

The cross-tab rounds both values to 0.01, and "other" collects the values outside the columns
shown:

| coded \ text | other | 0 | 0.25 | 0.5 | 0.75 | 1 | 1.5 | 2 | 2.5 | 3 | 4 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| other | 254 | 0 | 0 | 34 | 1 | 35 | 1 | 38 | 23 | 47 | 2 |
| 0.25 | 0 | 0 | 10 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 |
| 0.5 | 0 | 0 | 0 | 963 | 1 | 41 | 1 | 6 | 0 | 1 | 0 |
| 0.75 | 0 | 0 | 0 | 1 | 12 | 0 | 0 | 0 | 0 | 0 | 0 |
| 1 | 15 | 3 | 2 | 55 | 2 | 8,558 | 55 | 158 | 1 | 21 | 2 |
| 1.5 | 5 | 0 | 0 | 7 | 0 | 50 | 803 | 63 | 0 | 5 | 1 |
| 2 | 15 | 0 | 0 | 5 | 0 | 202 | 36 | 4,858 | 35 | 90 | 0 |
| 2.5 | 2 | 0 | 0 | 3 | 0 | 2 | 4 | 21 | 582 | 40 | 0 |
| 3 | 11 | 0 | 0 | 0 | 0 | 45 | 9 | 39 | 9 | 2,089 | 16 |
| 4 | 3 | 0 | 0 | 0 | 0 | 1 | 6 | 36 | 0 | 9 | 337 |

- **Weeks.** At 4 weeks to the month the column reads two weeks free as 0.5, which matches a
  coded 0.5 on 963 rows. For comparison, the first build converted weeks at 52/12: two weeks
  read as 0.46 against a coded 0.5 on 213 rows, overall agreement was 92.57% with 1,469 rows in
  disagreement, and of the 494 week offers on both sides the coded value equaled the weeks over
  4 on 403 and the 52/12 reading on 241. In the reader sample the coded field rounds 6, 5 and
  3 weeks each to 1 month.
- **Another offer in the text.** On 211 of the 1,302 disagreeing rows the coded value is one of
  the offers in the latest description, and the coded field follows a different offer from my
  chosen one, often for another lease ("1 MONTH FREE ON 13 MONTH LEASE, 2 MONTHS FREE ON 19").
  On 331 of the 623 disagreeing rows with a lease in the text, the coded `lease_term` differs
  from the text's lease.
- **Up to.** On 241 rows the column keeps the upper end of an "up to" offer or a range. In the
  reader sample the coded value lies below that end on 4 of 6 such ads.
- **Coded values absent from the text.** On the other 850 rows no offer in the latest
  description gives the coded value. Coded values such as 2.31, 1.11 and 1.13 look derived
  from prices. One ad (listing 4811052) states months at odds with its own gross and net
  prices.

The two largest off-diagonal cells fall mostly in the last group. Of the 158 rows coded 1 with
text 2, 126 are there, 18 are up-to offers and 14 have the coded value among their offers. Of
the 202 rows coded 2 with text 1, 124 are there, 4 are up-to offers and 74 have the coded value
among their offers.

To test whether another record of the listing holds the coded value, I read every record of
the 1,302 listings in the records file (`records.py`). On all 1,302 rows the coded value equals
`pricing.monthsFree` in the latest record, and I parse the description of that same record.
Only 4 of the listings have a second record, which carries the same value. On these rows the
record's coded field and its description disagree, and the records give no sign of which one
the listing agent wrote last.

## The readers

I drew 350 ads from the first build with seed 20261113 and gave them to Sonnet subagents in 14
batches of 25. The readers had the description alone, without the parser's value or the coded
one. For each ad they returned the free months, the lease, the kind, every offer in the text
and the price basis. They converted weeks at 52/12, as the first build did, so `score.py`
converts their 18 week values to 4 weeks a month before comparing them with the current parse.

After scoring the first build (v1) against the labels, I fixed the parser's misses found in the
labels:

- "a 1/2 month", ".50 free month" and decimals beyond a half such as 2.66;
- ordinal pairs such as "13th and 14th month free";
- "abatement" as a word for free;
- the offer tied to the listed price, chosen ahead of the others.

Then I moved weeks to 4 a month and added the rule for a unit left out of the building's
offer. The current parse (now) has all of these changes. Since the fixes came from the sampled
ads, v1's scores are the better guide to new text.

| sample | measure | v1 | now |
|---|---|---|---|
| found: 200 ads with a value and no coded one | readers read a rent offer above 0 | 199 | 199 |
| | parse gives months above 0 | 200 | 199 |
| | value within 0.1 of the readers' | 197 | 200 |
| | kind equal to the readers' | 192 | 193 |
| | lease equal, of 108 stated by both | 104 | 106 |
| missed: 100 ads with no count and free, concession or net effective in the text | readers give a count | 2 | 2 |
| | the parse gives that count | 0 | 1 |
| disagree: 50 ads where v1's text and coded values differ by over 0.1 | readers agree with the text | 44 | 49 |
| | readers agree with the coded value | 5 | 11 |
| | readers agree with neither | 1 | 1 |
| | the text equals the coded value | 0 | 11 |

In the found sample v1 gave months on all 200 ads. On listing 3069291 the text offers a month
free in the building and says "Incentives Do Not Apply" for the unit, and the reader reports no
offer. The unit rule now gives that ad none with 0 months, so the current values agree with the
readers on all 200. Of the current exact readings, the readers call 6 conditional.

In the missed sample the readers give a count on two ads. Listing 1508825 runs words together
("ENVOY1 MONTH FREE") and the current parse still misses it. Listing 3233614 offers "1 month
abatement", which the current parse reads. The missed sample came from 136,188 rows of the
first build. For v1, 2 in 100 puts the share with a missed count between 0.2% and 7% at 95%, and
for the current parse, 1 in 100 puts it between 0.03% and 5.4%. The readers mark 19 of the 100
unstated, against 17 for v1.

In the disagree sample the current text equals the coded value on 11 ads. On 5 of them v1 made
parser errors, and the fixes corrected them. The other 6 are week offers coded at 4 to the
month. On the rest the readers side with the text, apart from listing 2865689, which they call
unstated. Counting weeks at 4 to the month, the coded value is among the readers' offers on 19
of the 50.

Of the 39 sample ads still in disagreement, the coded value is among the parse's offers on 8,
and the text gives the upper end of an up-to offer on 6. On the other 25 no offer in the latest
description gives the coded value. Each of the 39 has a single record, and its coded field
equals the record's `pricing.monthsFree`. Of the 6 ads coded 1 with text 2, 1 has the coded
value among its offers, 1 is an up-to offer and 4 are of the third kind. Of the 7 coded 2 with
text 1, 4 have the coded value among their offers.

Over all 350 ads, `ask_basis_text` gives a basis on 174, and the readers agree on 160. Of the
171 ads it marks net, the readers call 157 net, 4 gross and 10 unstated, and they call all 3 of
its gross ads gross. Of the 176 ads it leaves unstated, they call 9 gross and 6 net. Most of
the readers' 16 gross ads state a gross amount beside the price, and I leave such amounts out
of the rule.

After adding the unit rule and the basis column, I gave a second set of ads to two Sonnet
subagents in batches of 23, again without the parse and with weeks at 4 to the month. The set
holds every L1 listing whose text leaves its unit out (6 ads), and 40 of the 1,365 gross-marked
texts in the extract, drawn with seed 20261114.

- The readers call all 40 gross-marked ads gross. They and the parse each give months above 0
  on 29 of them, and agree within 0.1 on all 29.
- On 5 of the 6 unit-excluded ads the readers find no offer for the unit, as the parse does.
  Only 3069291 had an offer to lose, and one of the 6 is a held-out ad. On listing 2254429 the
  line is "Co-Broke 15%, concession does not apply", about the broker's fee. That ad offers no
  free rent, and the rule gives it a stated zero where the readers give no reading.

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
| 2020 | 212,113 | 30,207 | 29,773 | 24,380 | 6,837 | 889 |
| 2021 | 193,715 | 5,981 | 51,682 | 1,226 | 1,839 | 979 |
| 2022 | 129,566 | 1,359 | 11,009 | 355 | 133 | 6 |
| 2023 | 144,785 | 2,399 | 17,031 | 312 | 123 | 106 |
| 2024 | 148,460 | 2,451 | 18,166 | 432 | 66 | 203 |
| 2025 | 145,685 | 2,688 | 19,077 | 202 | 60 | 386 |
| 2026 | 119,305 | 1,325 | 12,880 | 201 | 39 | 210 |

The 12 rows from 2011 and 2012 have no count. Before 2020 the text holds nearly every record
of concessions, with months on 85,051 rows lacking a coded value. From 2021 on the coded field
covers most offers, and the text adds a few hundred rows a year. One month is the commonest
value in every year and two months the next. Half months, two-week offers among them, rise from
148 rows in 2022 to 251 in 2026. Unstated rows peak at 6,837 in 2020 and fall to 39 in 2026.

## The target is net of free months

The task behind this note took L1's target for a gross ask, to be netted with the text's
months. The target is net already wherever the field is coded, and most text-only ads state a
net price.

- `docs/model/drift.md` gives `y` as the log of the final asking rent, net of any free months
  (line 157), and lists "Asks are net of free months, and price histories are gross" among its
  known issues (line 449).
- On 99.27% of the 160,936 coded rows with a page price and a lease term, `latest_ask` equals
  `page_price * (1 - months_free / lease_term)` within $2. The pipeline nets these rows.
- On 97.36% of the 112,159 text-only rows, `latest_ask` equals `page_price` within $2. The
  pipeline leaves these rows as listed. `ask_basis_text` marks 82,720 of them net and 917
  gross, and leaves 28,522 with no basis.
- Where a net-marked text-only ad states both a net and a gross amount, the page price is the
  net one. Of the 111,158 text-only rows with a page price and a text in the extract, 3,320 are
  marked net and state both amounts. On 2,940 of them `page_price` equals the net amount within
  $2, and on 148 the gross amount (`amounts.py`).
- The readers marked the basis net on 129 of the 200 found ads, gross on 12 and unstated on 59.

Netting the text-only asks by `months_free_text` would count the concession twice on most of
them. Gross asks enter L1's target only from the text-only rows with a gross price: 917 rows by
`ask_basis_text`, 1.1% of the 83,637 text-only rows with a basis, and 8.5% of the found ads with
a basis by the readers.

I take the 917 rows as a floor. Of the readers' 16 gross ads among the 350, the rule marks 3
gross and 4 net, and leaves 9 unstated. The readers call every gross-marked ad gross, 3 in the
first reading and 40 in the second. So the text-only rows likely hold many more gross asks
than 917.

## Uses

Before 2020 the column gives 85,051 rows a count of free months, where the coded field has
almost none. A fit could take the share of ads offering free months in a row's building or
neighborhood over the months before its price day as a measure of how soft the market was,
with the window ending at the price day as in `b0turnover`. The share would mean something
different from 2020 on, since from then most ads with an offer state it in the coded field
without repeating it in the text: in 2021 the text gives months on 5,981 rows and the coded
field on 51,682. A fit would need the text and coded months combined into one count, or a term
for each year. The unstated and none kinds mark
30,947 asks called net effective without a count and 85 asks with a concession denied or the
unit left out, and a fit could test whether either group prices apart from the rest. The Deals
page could show the free months and the gross rent beside a net ask, so a renter can tell a low
net ask from a low rent. For the 917 text-only rows marked gross, the column gives the months
to net the ask as the pipeline nets coded rows.

## Left open

- Words run together ("ENVOY1 MONTH FREE") go unread.
- The column reads the listing's latest record alone. An earlier record of the same listing
  may state a different offer, but only 4 of the 1,302 disagreeing listings have another
  record.
- I keep a single offer per text, so "first month free and last month free" gives 1 month,
  while "first and last month free" gives 2. None of the 129,041 texts with months in the
  extract uses the first form (`edges.py`).
- A count of free months followed by a broker's fee or a security deposit still gives the
  months ("1 month free broker fee", "1 month free security deposit"). The texts with months
  hold 1 of each, and both are real offers followed by a separate item: "1 Month Free Brokers
  Welcome" and "1 MONTH FREE Security deposit - $3998". `edges.py` matches "month" spelled
  out, so it misses abbreviations: a wider search finds a second broker text, "1 mo free
  Broker Fee".
- A negation after an offer ("1 month free not available") or before it ("no longer 1 month
  free") still gives the months. I found no such negation beside an offer in the texts with
  months.
- In "Price shown is gross; 1 month free" the parser ties the offer to the price, which marks
  the price net, while the text also calls the price gross. `ask_basis` gives such a text
  no basis, yet `choose` still ranks the offer as tied to the price. Of the texts with months,
  79 hold both readings, and 1 of them holds offers of different counts, where the rank could
  change the months.
- On 9,583 coded rows the text calls the price net effective, and the pipeline nets their page
  price by the coded months. I have not checked whether those texts mean the page price or a
  net figure written in the description.
- A stated gross amount gives no basis. I have not counted the 28,522 text-only rows without
  a basis for a stated gross amount.

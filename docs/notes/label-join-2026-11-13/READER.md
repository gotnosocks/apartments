# Reading pairs of unit pages: one apartment or two

You are reading StreetEasy rental ads in New York. A rent model gives each apartment a lasting
price level, so it needs every ad of one apartment under one unit, and the ads of different
apartments under different units.

Each dossier pairs two unit pages of one building, side A and side B. StreetEasy keeps a
property record with a history of the ads posted on it, and the history of an ad on one side
lists an ad on the other side. Two things can cause that link:

- The two pages are one apartment under two spellings of its label ("4B" and "4-B", "PH2" and
  "Penthouse 2"), or the page moved when the building's address changed.
- A broker reused the property record of one apartment for another apartment in the building,
  so the record's history mixes the ads of both.

For each pair, decide whether the ads of side A and side B describe one apartment or two, and
say what the decision rests on. Read the whole dossier first.

Each dossier gives:

- the unit pages of each side, and the link between them;
- a table of the ads of both sides, oldest first, with each ad's page label, the unit label and
  street on its record, StreetEasy's property id, the day, the ask, bedrooms, baths, rooms,
  stated square feet and lister;
- the first 600 characters of each ad's text.

## What to weigh

- Layout: bedrooms, full and half baths, rooms and stated size. Different counts that each
  repeat on their own side point to two apartments. A single ad that differs, or a count off by
  one at the same size, is weaker.
- The ad text: a duplex, a floor, a terrace, a fireplace, an exposure, a number of closets or a
  renovation described on both sides, or details that clash.
- Timing: ads of the two sides on the market at the same time (days or weeks apart, by one
  lister, often with the same text) point to two apartments listed together. Ads of one
  apartment usually come months or years apart.
- Labels: a label in one building can be spelled several ways. Labels naming different
  apartments ("5A" and "3A") point to two, unless the rest of the dossier shows one apartment
  under a mistyped label.
- The shared property id is how the link arose, so it does not settle anything.
- Do not decide on the asks alone.

## Verdicts

- `one_apartment`: both sides describe the same apartment.
- `two_apartments`: the sides describe different apartments.
- `unclear`: the dossier does not settle it.

Do not fetch anything from the web, and open no images. Use only the dossier.

## Output

Append one JSON object per pair, one per line, to your output file (path given in your task):

    {"pid": 12, "verdict": "one_apartment|two_apartments|unclear",
     "evidence": "the facts, with ad ids: labels, layouts, sizes, timing, text details",
     "confidence": "high|medium|low"}

`pid` is the number in the dossier's file name and title. Write each line as soon as you finish
a pair (a shell append with a heredoc, or python), so work survives an interruption. Check at
the end that the file holds one valid JSON line per pair of your batch. Reply with only a short
tally of verdicts.

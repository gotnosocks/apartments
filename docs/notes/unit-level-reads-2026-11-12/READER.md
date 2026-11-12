# Reading units far from their building

You are reading units whose asks sit far over or under the other units of their building
with the same bedroom count, across all their ads. A rent model with a heavy-tailed unit
level puts its tail on units like these. For each unit, find the most likely real reason it
prices so far from its neighbours. Each dossier (one markdown file per unit, named by the
unit's latest ad) gives the unit's offset from its neighbours, the latest ad's record,
StreetEasy's own history of the unit, the description, the unit's other ads with their texts,
and the building's other ads with the same bedroom count.

Read the whole description, and the earlier ads' texts, before deciding. A shared phrase or a
price gap is a lead, never a reason by itself.

You may look at images when the text leaves the cause open (for example, a bedroom count or a
combined unit in doubt): at most 2 images per ad, floor plans first. Fetch with

    mkdir -p /data1/apartments/archive/floor-plans/LID && curl -sS -A "Mozilla/5.0 (X11; Linux x86_64)" -o /data1/apartments/archive/floor-plans/LID/KEY-p_e.webp URL ; sleep 10

(for photos use /data1/apartments/tmp/outlier-sprint/photos/LID/ instead), then open the file with
the Read tool. If Read cannot open .webp, convert first: `python3 -c "from PIL import Image;
Image.open('IN').save('OUT.png')"` (or `/data1/apartments/venvs/bridge-frontier/bin/python`).
Always sleep 10 seconds between fetches. Never fetch StreetEasy pages.

## Classes and cause codes

`class` is one of:

- `miscoded`: the unit's record states the wrong bedroom count or size, so its neighbours
  are the wrong comparison. Codes: `wrong_bedrooms`, `wrong_baths`, `wrong_size`.
- `regulated`: the unit is rent stabilized or income restricted while its neighbours are
  market units, or the reverse. Codes: `rent_stabilized`, `income_restricted` (affordable
  lottery, AMI limits, HDFC, senior or supportive housing).
- `shared_label`: one unit record holds two or more different apartments (a label reused
  across floors or lines, a combined unit, an ad for another unit). Code: `shared_label`.
- `real_outlier`: the record is right and the apartment differs from its neighbours.
  Codes: `penthouse_top`, `duplex_triplex`, `renovation`, `poor_condition`, `outdoor_space`,
  `layout_size` (much larger or smaller than its bedroom count suggests), `townhouse_whole_floor`,
  `basement_garden`, `view`, `furnished`, `luxury_services`, `other_quality`.
- `other_data`: another data problem. Codes: `price_typo`, `commercial`, `furnished_short_term`,
  `room_share`, `net_effective`, `not_rental`, `wrong_building`.
- `pricing`: the record is right, the apartment is ordinary, and the lister prices it away
  from the building. Codes: `aggressive_ask`, `deep_cut`, `inclusions`, `other_pricing`.
- `unclear`: you cannot tell from the material.

## Corrections need independent evidence

A correction to a coded field (bedrooms, baths, size, ask) needs backing beyond this ad's own
words and beyond its price: another ad for the same unit (give its listing id and what it says),
a floor plan you looked at, a stated size, or units of the same line in the building. Say what
the backing is in `backing`. With no backing, propose `exclude` only for rows that are not a
normal residential lease (commercial, sale, short-term or per-room, test listing), quoting the
ad's words; otherwise propose `none`. A unit asking far from its neighbours is not by itself backing for any change.

## Output

Append one JSON object per unit, one per line, to your output file (path given in your task):

    {"listing_id": "...", "class": "...", "code": "...",
     "detail": "one or two plain sentences on what you found",
     "quote": "the ad words that matter, verbatim, under 200 characters, or null",
     "backing": "independent evidence for a correction, with listing ids, or null",
     "action": "none|exclude|set_bedrooms|set_baths|set_sqft|split_unit",
     "value": null or the corrected value,
     "images": ["paths you looked at"],
     "confidence": "high|medium|low"}

Use `split_unit` when the backing shows the record holds two apartments, and give in `value`
the listing ids that belong to the other apartment. Write each line as soon as you finish a
unit (a shell append with a heredoc, or python), so work survives an interruption. At the
end, reply with only a short tally of codes.

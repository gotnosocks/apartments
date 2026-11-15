# Reading the worst misses like a broker

Ben asked on 2026-11-15 for the model to be judged the way someone who knows the market would
judge it. A renter, an agent or a broker looking down the list of ads the model priced worst
should not be able to point at what those ads share and say the model obviously missed it. When
they can, the shared trait is a candidate feature. This page sets out how each read runs.

## When to read

After each fit that passes the gate, on its held-out ads from the latest split. Held-out ads
keep the read clear of the target leak in `docs/leak-free-scoring.md`, because their rents
never entered the fit.

Choosing a feature from these ads' errors still biases any later score on the same ads, the
hazard that `docs/leak-free-scoring.md` calls data rules chosen with rents in view. So each
read picks its ads from half of the held-out buildings, drawn by a seed in the read's note,
and the free check and the fit's score for a candidate use the other half.

## Picking the ads

`python -m rentfrontier.drift_score RUN` writes `pred_scores.npz` into the run folder. Its
`cdf` gives each held-out ad's predictive probability of a rent below the ask.

- The **ask far above** set holds ads whose `cdf` is above 0.99: asks the model thought too
  high to happen.
- The **ask far below** set holds ads whose `cdf` is below 0.01. These matter most for Deals,
  since every one of them shows as a bargain, and a missed feature makes it a false one.
- The **control** set is a random draw of held-out ads with `cdf` between 0.25 and 0.75.

Before reading, set aside ads the data rules would drop or fix (a commercial space, a wrong
unit size, a net-effective ask). Those go to the data thread's quarantine work, not to the
feature list.

## Reading

Readers read the whole ad, with its photos and floor plan where they are stored, plus the
building's fields, before writing down any reason. They read in groups of about 20 from one
set, mixed with control ads, and do not know which ads are which. Grouping matters because an
expert spots a trait by seeing it again and again, and one strange ad rarely shows a feature.

For each ad a reader writes down short traits a broker would price: floor and light, the
view, a walkup's flights, the block's noise, an elevated train outside, the renovation, the
layout, a garden or terrace, the rent's terms. Bulk reading runs on Sonnet or Haiku. The
default model groups the traits into candidates.

## Keeping a candidate

A candidate goes forward when it is much more common in a miss set than in the control set,
with the counts and an interval in the read's note. A trait common in both sets gets dropped.
A trait the model already has as a term stays only when the read shows the term coded wrong or
too coarse, such as a floor field that reads "PH" as missing.

## From candidate to term

1. Code the trait for every row from fields or text, without the rent.
2. Check, at no cost, how much of the error on the unread half of the held-out ads the coded
   trait explains, against a null from shuffled labels
   (`explained` above the null's 95th percentile).
3. Write the fit's note with predictions, then fit it as a single change, under the rules in
   `CLAUDE.md`. Ben cares most about terms that change which ads show as deals, so a term with
   a small effect on few ads waits.

Each read gets a note under `docs/notes/`, with the ads read, the traits found, the counts and
what happened to each candidate.

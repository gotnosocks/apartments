"""Record manual full-description review of the twelve income-screen candidates.

All findings are unresolved annotations bound to their exact source observations.
No feature extraction, price correction, historical eligibility assignment or
main-selection change is performed.
"""

import argparse
from pathlib import Path
import json

from apartments import source_issues
from apartments.research_pipeline import _verified_bundle, digest

SOURCE_HASH = "d244ca6710e080e18059f1b3279a373e187ea38fb4219c51deff7e49f4604717"
EVIDENCE_HASH = "79308dfdbefd7fe8a03630bdd048fa742d0f7cd3335b82f25da0575a9d9b7e08"
SCREEN_HASH = "d78ffa03d01381754a4a52f538cbab5ec81a96f5c3c005f06b289ba0b3bc1f10"
TEMPORAL = (
    "The complete same-advertisement description was reviewed at its September 2026 "
    "capture. These retrospective claims do not establish eligibility, composition "
    "or offer terms at the earlier initial asking-price event. No effective date, "
    "legal classification or replacement feature value is assigned."
)


def specifications(cases):
    by_ad = {r["source_listing_id"]: r for r in cases}
    result = []

    def add(ad, kind, message, literals, **observed):
        row = by_ad[ad]
        result.append(
            {
                "audit_id": row["audit_id"],
                "kind": kind,
                "message": message,
                "temporal_scope": TEMPORAL,
                "literals": literals,
                "observed_fields": {
                    "asking_rent": row["asking_rent"],
                    "period": row["period"],
                    **observed,
                },
            }
        )

    for ad, minimum, maximum in (
        ("4758015", "$77,760", "$90,720 to $103,680"),
        ("4761346", "$83,314", "$83,314 to $103,680"),
    ):
        add(
            ad,
            "advertised_income_ceiling_dollars_unmodeled",
            "The own offer requires a household income bracket and prohibits guarantors. "
            "Its minimum and household-maximum wording is retained literally; the ranges "
            "do not establish a separate threshold for each household size or a discount coefficient.",
            [
                f"Minimum Annual Income: {minimum}",
                f"1-2 Person Household Maximum Annual Income: {maximum} (amounts represented)",
                "NO guarantors allowed.",
            ],
        )
    add(
        "4276224",
        "advertised_income_ceiling_dollars_unmodeled",
        "The co-op offer explicitly requires one tenant to earn under $163,150. "
        "The two-tenant $186,540 wording omits the comparison operator; it is not silently "
        "converted into a precise upper-bound feasibility rule.",
        [
            "This coop building has an income restriction in order to rent.  One tenant has to make under $163,150.  Two tenants have to make a combined income of $186,540."
        ],
    )
    add(
        "4160254",
        "advertised_income_ceiling_dollars_unmodeled",
        "The offer explicitly requires income within a bracket, with minimum $105,000 "
        "and a one-person maximum $176,220. Other household sizes and historical applicability remain unknown.",
        [
            "You MUST be within income specified below to qualify!",
            "Minimum Income: $105,000",
            "Maximum Income: 1 Person People: $176,220",
        ],
    )
    add(
        "4488024",
        "advertised_income_ceiling_dollars_unmodeled",
        "The offer states 165% AMI, one/two-person dollar ceilings and a rent-stabilized "
        "lease. These are source claims, not independently established legal status; "
        "this program must not be pooled with 120% AMI offers without assessment.",
        [
            "This is an income restricted apartment at 165% AMI. Annual income must be below $179,355 (for one person) or $205,095 (for two people).",
            "The apartment is offered with a RENT-STABILIZED lease.",
        ],
    )
    for ad, phrase in (
        ("4968706", "120 percent Area Median Income (AMI) max income"),
        ("4817705", "120 percent Area Median Income (AMI) maximum income"),
        (
            "4837062",
            "max income per house hold of 120 percent Area Median Income (AMI)",
        ),
        (
            "4902655",
            "max income per house hold of 120 percent Area Median Income (AMI)",
        ),
    ):
        add(
            ad,
            "advertised_income_ceiling_ami_unmodeled",
            "The own HDFC offer explicitly describes a 120% AMI maximum. Its guarantor "
            "condition below 40 times rent is a distinct application requirement, not "
            "a second upper ceiling. No historical AMI schedule or rent discount is established.",
            [
                "This is HDFC",
                phrase,
                "use a guarantor if their income is below 40 times the rent.",
            ],
        )
    add(
        "4810936",
        "advertised_ami_eligibility_boundary_unspecified",
        "The own HDFC offer requires meeting 120% AMI but does not explicitly say "
        "maximum, minimum or equality. Preserve that ambiguity separately from its "
        "conditional guarantor requirement below 40 times rent.",
        [
            "This is HDFC",
            "must meet the 120 percent Area Median Income (AMI) and use a guarantor if their income is below 40 times the rent.",
        ],
    )
    add(
        "4780384",
        "advertised_ami_eligibility_boundary_unspecified",
        "The own offer requires a guarantor and meeting 120% AMI, without an explicit "
        "boundary operator. This description does not itself name HDFC; do not copy "
        "program labels or the conditional guarantor wording from other building ads.",
        [
            "Applicants who wish to qualify must use a guarantor and meet the 120 percent Area Median Income (AMI) ."
        ],
    )
    add(
        "3705384",
        "advertised_income_restriction_terms_unspecified",
        "The offer explicitly refers to income restrictions for this unit, but gives "
        "no thresholds, direction or program. It supports a restriction claim with unknown terms.",
        ["Please reach out for the income restrictions for this unit."],
    )
    for ad, floor, phrase in (
        ("4810936", 1, "Apartment 1A on the second floor"),
        ("4817705", 2, "Apartment 2D on the third floor"),
        ("4902655", 1, "Apartment 1b on the second floor"),
        ("4968706", 1, "Apartment 1C on the third floor"),
    ):
        add(
            ad,
            "label_proxy_prose_floor_disagreement",
            "The fitted listed floor comes from a unit-label proxy, while the own "
            "description explicitly locates the named apartment on a different floor. "
            "This may reflect numbering or erroneous prose. Preserve both claims; "
            "do not infer a building-wide offset or a physical-floor correction.",
            [phrase],
            listed_floor=floor,
        )
    for ad in ("4837062", "4902655"):
        add(
            ad,
            "internally_conflicting_bedroom_description",
            "The fitted count is two bedrooms, but the own description calls the "
            "same offer both one bedroom and two bedroom. Neither phrase alone "
            "establishes a correction; layout or other exact-unit evidence is needed.",
            [
                "a stunning, one bedroom",
                "This two bedroom has a wonderful pre war charm.",
            ],
            bedrooms=2.0,
        )
    add(
        "4276224",
        "furnished_short_term_utilities_offer_scope",
        "This offer is furnished and short-term only, ending April 30 without a "
        "stated year, with utilities included. Its package differs from a standard "
        "unfurnished annual offer; do not attribute its price to eligibility alone.",
        [
            "FURNISHED, Short-Term only rental till April 30th.",
            "This unit includes all utilities",
        ],
    )
    if (
        len(by_ad) != 12
        or len(result) != 19
        or {r["audit_id"] for r in result} != {r["audit_id"] for r in cases}
    ):
        raise ValueError(
            "Manual review does not cover the exact twelve screen candidates"
        )
    return result


def run(dataset, evidence, screen, output, reviewed_at):
    dataset, evidence, screen, output = map(Path, (dataset, evidence, screen, output))
    if [digest(p / "complete.json") for p in (dataset, evidence, screen)] != [
        SOURCE_HASH,
        EVIDENCE_HASH,
        SCREEN_HASH,
    ]:
        raise ValueError("Expected the reviewed source, evidence and frozen screen")
    _, files = _verified_bundle(screen, retain={"cases.jsonl"})
    cases = [json.loads(line) for line in files["cases.jsonl"].splitlines()]
    notes = source_issues.publish_source_issues(
        dataset,
        evidence,
        specifications(cases),
        output,
        reviewed_at=reviewed_at,
        reviewer="Codex: full own-description review of all twelve income-screen candidates",
    )
    restored = source_issues.load_source_issues(dataset, output, evidence=evidence)
    if notes != restored:
        raise ValueError(
            "Published income review differs from independently loaded annotations"
        )
    print(
        json.dumps(
            {
                "observations": len(notes),
                "issues": sum(len(n["issues"]) for n in notes.values()),
                "manifest_sha256": digest(output / "complete.json"),
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("dataset", "evidence", "screen", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--reviewed-at", required=True)
    run(**vars(parser.parse_args()))

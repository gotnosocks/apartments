"""Compare source-claim grammar to a fixed, separately labeled source sample."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from apartments import outdoor_scope
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle


def run(review, output):
    rm, rf = _verified_bundle(review, retain={"review.json"})
    cases = json.loads(rf["review.json"])["cases"]
    confusion, results, extras = Counter(), [], []
    for case in cases:
        text = case["description"]
        if hashlib.sha256(text.encode()).hexdigest() != case["description_sha256"]:
            raise ValueError("Reviewed description hash mismatch")
        claims = outdoor_scope.scope_text(text)
        used = set()
        for label in case["annotations"]:
            if text[label["start"] : label["end"]] != label["text"]:
                raise ValueError("Review offsets do not bind description")
            found = [
                (i, c)
                for i, c in enumerate(claims)
                if c["noun_start"] == label["start"] and c["noun_end"] == label["end"]
            ]
            if len(found) > 1:
                raise ValueError("Duplicate mention span")
            prediction = found[0][1] if found else None
            if found:
                used.add(found[0][0])
            predicted = prediction["scope"] if prediction else "missing_mention"
            confusion[label["scope"], predicted] += 1
            results.append(
                {
                    "case_id": case["case_id"],
                    "audit_id": case["audit_id"],
                    "source_listing_id": case["source_listing_id"],
                    "capture_id": case["capture_id"],
                    "label": label,
                    "prediction": prediction,
                    "scope_matches": predicted == label["scope"],
                }
            )
        extras.extend(
            {"case_id": case["case_id"], "audit_id": case["audit_id"], "claim": claim}
            for i, claim in enumerate(claims)
            if i not in used
        )
    positive = {"private_explicit", "unit_access"}
    promoted = [
        r for r in results if r["prediction"] and r["prediction"]["scope"] in positive
    ]
    summary = {
        "cases": len(cases),
        "labeled_mentions": len(results),
        "exact_scope_matches": sum(r["scope_matches"] for r in results),
        "missing_mentions": sum(r["prediction"] is None for r in results),
        "unlabeled_extracted_mentions": len(extras),
        "matched_unit_positive_claims": len(promoted),
        "matched_unit_positive_claims_with_positive_label": sum(
            r["label"]["scope"] in positive for r in promoted
        ),
        "unlabeled_unit_positive_claims": sum(
            r["claim"]["scope"] in positive for r in extras
        ),
        "confusion": [
            {"label": a, "prediction": b, "count": n}
            for (a, b), n in sorted(confusion.items())
        ],
        "interpretation": "Agreement with agent source labels on a lexically enriched development sample; not population accuracy or physical amenity ground truth.",
    }
    return publish_bundle(
        output,
        {
            "summary.json": canonical(summary) + "\n",
            "comparisons.jsonl": "".join(canonical(r) + "\n" for r in results),
            "unlabeled-mentions.jsonl": "".join(canonical(r) + "\n" for r in extras),
            "outdoor_scope.py": Path(outdoor_scope.__file__).read_text(),
            "evaluation.py": Path(__file__).read_text(),
        },
        {
            "version": "outdoor-scope-evaluation-v1",
            "extractor_version": outdoor_scope.VERSION,
            "review_manifest": rm,
            "summary": summary,
            "implementation_sha256": {
                "outdoor_scope.py": digest(outdoor_scope.__file__),
                "evaluation.py": digest(__file__),
            },
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("review", "output"):
        parser.add_argument("--" + key, type=Path, required=True)
    result = run(**vars(parser.parse_args()))
    print(canonical(result["summary"]))

"""Private SDK-only cloud queries and one writer for the rental review utility."""

import os
from pathlib import Path

import modal

ROOT = Path(__file__).resolve().parents[1]
app = modal.App("chelsea-rental-review")
volume = modal.Volume.from_name("chelsea-archive")
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "duckdb==1.5.5", "pyarrow==24.0.0", "jsonpatch==1.33", "parsel==1.10.0"
    )
    .env({"PYTHONPATH": "/root/src", "OMP_NUM_THREADS": "2", "REVIEW_READ_ONLY": "1"})
    .add_local_dir(
        ROOT / "src/apartments", "/root/src/apartments", ignore=["__pycache__"]
    )
    .add_local_dir(
        ROOT / "src/streeteasy_archive",
        "/root/src/streeteasy_archive",
        ignore=["__pycache__"],
    )
)
_service = None


@app.function(
    image=image,
    cpu=1,
    memory=2048,
    timeout=600,
    volumes={"/archive": volume},
    max_containers=1,
    min_containers=0,
    scaledown_window=120,
    retries=0,
)
def review(action: str, args: dict | None = None):
    global _service
    if os.environ.get("REVIEW_READ_ONLY") == "1" and action not in {
        "exclusions",
        "overview",
        "observations",
        "observation",
        "events",
        "activity",
        "unit_candidates",
        "unit_inspect",
        "unit_mapping",
        "unit_batches",
        "unit_proposal",
    }:
        return {
            "ok": False,
            "error": "Review writes on Modal are frozen for migration to thelio. Reload the local app after cutover.",
        }
    from apartments.review_service import ReviewService

    if _service is None:
        _service = ReviewService(
            "/archive/datasets/chelsea-granular-20260916",
            "/archive/reviews/chelsea-granular-20260916",
        )
    try:
        result = _service.dispatch(action, args)
        if action in (
            "unit_merge",
            "unit_separate",
            "unit_undo_separate",
            "unit_undo",
            "unit_association_preview",
            "unit_association_apply",
            "unit_association_undo",
            "preview",
            "cohort_preview",
            "apply",
            "review",
            "listing_inclusion",
            "parser_issue",
            "retract",
        ):
            volume.commit()
        return {"ok": True, "result": result}
    except (ValueError, KeyError, TypeError) as e:
        return {"ok": False, "error": str(e)}

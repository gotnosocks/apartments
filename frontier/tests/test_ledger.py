import json

from rentfrontier import features, ledger

REST = "-rows-abc1234-x-2060-100w600d-gv1006"
M = "m7-nocurves-bedtime"


def rec(model, fs, rows=100):
    name = f"{model}-{fs}{REST}"
    return name, {
        "source_run": name,
        "model": model,
        "feature_set": fs,
        "rows": rows,
        "_dir": name,
    }


def loo(*records):
    return dict(rec(*r) for r in records)


def test_pairs_feature_set_with_its_base_and_model_term_with_its_parent():
    runs = loo(
        (M, "nb3-coded-v2"),
        (M, "nb3-lines-v1"),
        (M + "-yearnoise", "nb3-coded-v2"),
        (M, "nb3-loud-v1"),  # no reference needed beyond the base
        ("m5-other", "nb3-retail-v1"),  # its base never ran with m5-other
    )
    found = {(c, t["source_run"], r["source_run"]) for c, t, r in ledger.pairs(runs)}
    assert features.FEATURE_SETS["nb3-lines-v1"].keywords["base"] == "nb3-coded-v2"
    assert found == {
        ("nb3-lines-v1", f"{M}-nb3-lines-v1{REST}", f"{M}-nb3-coded-v2{REST}"),
        ("nb3-loud-v1", f"{M}-nb3-loud-v1{REST}", f"{M}-nb3-coded-v2{REST}"),
        ("+yearnoise", f"{M}-yearnoise-nb3-coded-v2{REST}", f"{M}-nb3-coded-v2{REST}"),
    }


def test_rows_verdict_and_retest(tmp_path, monkeypatch):
    runs = loo(
        (M, "nb3-coded-v2"),
        (M, "nb3-lines-v1"),
        (M, "nb3-bedsize-v1"),
        (M + "-yearnoise", "nb3-coded-v2"),
    )
    for name in runs:
        (tmp_path / name).mkdir()
        (tmp_path / name / "result.json").write_text(
            json.dumps({"dataset": "/x/old-dataset", "started_at": "2026-10-06T01:00"})
        )
    monkeypatch.setattr(ledger.leaderboard, "RUNS", tmp_path)
    diffs = {"nb3-lines-v1": 21.6, "nb3-bedsize-v1": -40.0, "yearnoise": 745.0}

    def paired(a, b):
        d = next(v for k, v in diffs.items() if f"-{k}-" in a)
        return d, 10.2, 13.9  # combined SE 17.2

    notes = {"nb3-lines-v1": {"kind": "location", "pr": 357, "about": "lines"}}
    out = {e["change"]: e for e in ledger.rows(runs, notes, "old-dataset", paired)}
    assert round(out["nb3-lines-v1"]["se"], 1) == 17.2
    assert out["nb3-lines-v1"]["verdict"] == "no clear gain"
    assert out["nb3-lines-v1"]["retest"] == "next neighbourhood"
    assert out["nb3-bedsize-v1"]["verdict"] == "worse"
    assert out["nb3-bedsize-v1"]["retest"] == ""
    assert out["+yearnoise"]["verdict"] == "gain"

    out = {e["change"]: e for e in ledger.rows(runs, notes, "new-dataset", paired)}
    assert out["nb3-lines-v1"]["retest"] == "due, location"
    assert out["nb3-bedsize-v1"]["retest"] == "due"
    assert out["+yearnoise"]["retest"] == ""
    text = ledger.markdown(list(out.values()), "new-dataset")
    assert (
        "| `nb3-lines-v1` | lines | location | +21.6 ± 17.2 | no clear gain |" in text
    )


def test_notes_name_known_feature_sets():
    notes = json.loads(ledger.NOTES.read_text())["changes"]
    for change in notes:
        if not change.startswith("+"):
            assert change in features.FEATURE_SETS, change

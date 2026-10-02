import json

import pytest
from rentfrontier import elegance


def answer(shown, verdict, reason="r"):
    return {"shown": shown, "verdict": verdict, "reason": reason}


def test_agreeing_judges_decide_and_disagreeing_ones_tie():
    a, b = "m1/f", "m2/f"
    agree = elegance.combine(answer([a, b], b), answer([b, a], b))
    assert agree["designs"] == [a, b] and agree["verdict"] == b
    split = elegance.combine(answer([a, b], a), answer([b, a], b))
    assert split["verdict"] == "equal" and "disagreed" in split["reason"]
    with pytest.raises(SystemExit):  # both judges must not see the same order
        elegance.combine(answer([a, b], a), answer([a, b], a))


def test_compare_reads_the_recorded_judgements(tmp_path):
    a, b, c = "m1/f", "m2/f", "m3/f"
    path = tmp_path / "j.jsonl"
    lines = [
        elegance.combine(answer([a, b], a), answer([b, a], a)),
        elegance.combine(answer([b, c], "equal"), answer([c, b], "equal")),
    ]
    path.write_text("".join(json.dumps(x) + "\n" for x in lines))
    table = elegance.judgements(path)
    assert elegance.compare(a, b, table) == 1
    assert elegance.compare(b, a, table) == -1
    assert elegance.compare(b, c, table) == 0
    assert elegance.compare(a, c, table) is None
    assert elegance.compare(a, a, table) == 0
    assert [j["verdict"] for j in elegance.for_design(b, table)] == [
        "less elegant",
        "equal",
    ]


def test_a_pair_judged_twice_is_refused(tmp_path):
    a, b = "m1/f", "m2/f"
    line = json.dumps(elegance.combine(answer([a, b], a), answer([b, a], a)))
    path = tmp_path / "j.jsonl"
    path.write_text(line + "\n" + line + "\n")
    with pytest.raises(ValueError, match="two elegance judgements"):
        elegance.judgements(path)


def test_the_brief_is_blind_and_names_both_designs():
    text = elegance.brief("m7-nocurves-floorslope/unitfacing-v5", "m5-nocurves/x")
    assert "m7-nocurves-floorslope/unitfacing-v5" in text and "m5-nocurves/x" in text
    assert "Do NOT look at scores" in text


def test_the_brief_asks_for_statistical_elegance():
    text = elegance.brief("a/x", "b/y")
    assert "generative story" in text and "special cases" in text
    assert "renter" not in text.lower()
    j = elegance.combine(answer(["a/x", "b/y"], "a/x"), answer(["b/y", "a/x"], "a/x"))
    assert j["brief"] == elegance.BRIEF_VERSION

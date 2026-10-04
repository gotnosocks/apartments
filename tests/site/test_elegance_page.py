"""The elegance page: standings, a design filter and pages (573 pairs on 2026-10-04)."""

import json

from apartments.site.research import elegance_standings
from apartments.site.web import create_app


def many_pairs(research_file, n=120):
    data = json.loads(research_file.read_text())
    data["elegance_judgements"] = [
        {
            "designs": [f"m-a{i}/f", "m-test/unitdesc-v1"],
            "verdict": "m-test/unitdesc-v1" if i % 2 else "equal",
            "reason": f"pair {i}",
            "date": "2026-10-04",
            "judges": [],
        }
        for i in range(n)
    ]
    research_file.write_text(json.dumps(data))


def test_judgements_are_paged_and_filterable(site_root, research_file):
    many_pairs(research_file)
    client = create_app(site_root, research_data=research_file).test_client()
    first = client.get("/research/elegance").get_data(as_text=True)
    assert first.count('class="judgement"') == 50 and "page 1 of 3" in first
    last = client.get("/research/elegance?page=3").get_data(as_text=True)
    assert last.count('class="judgement"') == 20
    one = client.get("/research/elegance?design=m-a7/").get_data(as_text=True)
    assert one.count('class="judgement"') == 1 and "1 of 120 pairs" in one
    none = client.get("/research/elegance?design=nothing").get_data(as_text=True)
    assert "No judged pair involves a design matching" in none
    assert client.get("/research/elegance?page=x").status_code == 200


def test_standings_count_each_designs_verdicts():
    # ranked by more minus less: d (2 - 0) above a (3 - 2) though a won more often
    pairs = [
        {"designs": [{"id": "a"}, {"id": "b"}], "verdict": "a"},
        {"designs": [{"id": "a"}, {"id": "c"}], "verdict": "a"},
        {"designs": [{"id": "a"}, {"id": "e"}], "verdict": "a"},
        {"designs": [{"id": "d"}, {"id": "a"}], "verdict": "d"},
        {"designs": [{"id": "d"}, {"id": "a"}], "verdict": "d"},
    ]
    assert [r["id"] for r in elegance_standings(pairs)] == ["d", "a", "b", "c", "e"]

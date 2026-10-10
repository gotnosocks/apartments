"""The served fit's own accuracy checks on the validation and served-model pages."""

import json

from apartments.site.web import create_app


def with_checks(research_file):
    data = json.loads(research_file.read_text())
    served = next(e for e in data["entries"] if e["id"].startswith("m-test/"))
    served["psis"].update(
        k_share=0.0113,
        k_over=882,
        k_threshold=2 / 3,
        validation={
            "heldout_rows": 8664,
            "heldout_mean_lpd": 1.2454,
            "psis_mean_lpd_multi_row_units": 1.2507,
        },
    )
    served["variance"] = dict(
        served.get("variance") or {},
        descriptive={
            "mean": 0.30,
            "median": 0.221,
            "lower_90": 0.214,
            "upper_90": 0.227,
        },
    )
    served["new_unit_coverage"] = {
        "rows": 1234,
        "cover_80": 0.791,
        "cover_95": 0.948,
        "se_80": 0.01,
        "se_95": 0.006,
    }
    research_file.write_text(json.dumps(data))


def test_validation_page_leads_with_the_served_fits_checks(site_root, research_file):
    with_checks(research_file)
    client = create_app(site_root, research_data=research_file).test_client()
    html = " ".join(client.get("/research/validation").get_data(as_text=True).split())
    assert 'id="served-checks"' in html
    assert "1.1% of the listings in the fit (882)" in html and "above 0.67" in html
    assert "1.245 per listing on the 8,664 listings" in html
    assert "a gap of -0.005" in html
    # the retired PyMC reference comparison is gone (Fable framework, 2026-10-10)
    assert "held-out listings the" not in html and "(reference)" not in html
    assert "Unseen apartments" not in html
    # the fit's own descriptive share, as the median over draws, not the mean
    assert "Descriptive share</dt> <dd>22.1% <span" in html and "21.4% to 22.7%" in html
    assert "30.0%" not in html
    assert "79% of asks inside the 80% range and 95% inside the 95% range" in html
    assert "on 1,234 asks" in html


def test_served_model_page_shows_the_same_checks(site_root, research_file):
    with_checks(research_file)
    client = create_app(site_root, research_data=research_file).test_client()
    html = " ".join(client.get("/research/model").get_data(as_text=True).split())
    assert "Is the accuracy score trustworthy, and how much does it explain?" in html
    assert (
        "1.1% of the listings in the fit (882)" in html
        and "Held-out cross-check" in html
    )


def test_checks_left_out_when_the_entry_lacks_them(client):
    html = client.get("/research/model").get_data(as_text=True)
    assert "Held-out cross-check" not in html and "Pareto k</a> above" not in html
    # the slots stay empty rather than borrow another fit's numbers
    flat = " ".join(html.split())
    assert flat.count("not yet measured for this fit") == 2


def test_descriptive_share_falls_back_to_the_mean(site_root, research_file):
    data = json.loads(research_file.read_text())
    served = next(e for e in data["entries"] if e["id"].startswith("m-test/"))
    served["variance"] = {"descriptive": {"mean": 0.25}}
    research_file.write_text(json.dumps(data))
    client = create_app(site_root, research_data=research_file).test_client()
    html = " ".join(client.get("/research/model").get_data(as_text=True).split())
    assert "Descriptive share</dt> <dd>25.0%." in html


def test_board_sorts_by_descriptive_share(site_root, research_file):
    data = json.loads(research_file.read_text())
    scored = [e for e in data["entries"] if e.get("psis")][:2]
    for e, share in zip(scored, (0.4, 0.1)):
        e["variance"] = dict(e.get("variance") or {}, descriptive={"median": share})
    research_file.write_text(json.dumps(data))
    client = create_app(site_root, research_data=research_file).test_client()
    html = client.get("/research/board?sort=descriptive").get_data(as_text=True)
    assert "Descriptive share" in html
    assert html.index("10.0%") < html.index("40.0%")  # lower is better, first

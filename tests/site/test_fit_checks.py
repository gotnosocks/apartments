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
    data["reference"] = {"id": "promoted", "label": "Promoted PyMC model (reference)"}
    served["splits"]["rows"]["paired_rows"] = 5264
    research_file.write_text(json.dumps(data))


def test_validation_page_leads_with_the_served_fits_checks(site_root, research_file):
    with_checks(research_file)
    client = create_app(site_root, research_data=research_file).test_client()
    html = " ".join(client.get("/research/validation").get_data(as_text=True).split())
    assert 'id="served-checks"' in html
    assert "1.1% of the listings in the fit (882)" in html and "above 0.67" in html
    assert "1.245 per listing on the 8,664 listings" in html
    assert "a gap of -0.005" in html
    assert "-12.5 ± 30.1 on the 5,264 held-out listings the" in html
    assert "Promoted PyMC model (reference)" in html


def test_served_model_page_shows_the_same_checks(site_root, research_file):
    with_checks(research_file)
    client = create_app(site_root, research_data=research_file).test_client()
    html = " ".join(client.get("/research/model").get_data(as_text=True).split())
    assert "Is the accuracy score trustworthy?" in html
    assert (
        "1.1% of the listings in the fit (882)" in html
        and "Held-out cross-check" in html
    )


def test_checks_left_out_when_the_entry_lacks_them(client):
    html = client.get("/research/model").get_data(as_text=True)
    assert "Held-out cross-check" not in html and "Pareto k</a> above" not in html

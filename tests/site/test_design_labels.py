"""Designs labelled by what they do (Modeling, 2026-10-04)."""

from apartments.site import anatomy


def test_label_says_what_the_design_adds():
    a = anatomy.describe(
        {
            "name": "x",
            "building_walk": True,
            "trend_knot_months": 3,
            "unit_t": True,
            "feature_slopes": ["log_floor"],
            "beta_sd": 0.5,
        }
    )
    assert a.label == (
        "trend quarterly · building drift 6 mo · own prices floor · "
        "heavy-tailed apartment premium"
    )
    assert anatomy.describe({"name": "m0", "beta_sd": 0.5}).label == "basic hierarchy"
    ladder = anatomy.describe({"name": "L0", "trend": False, "features": False})
    assert ladder.label.startswith("no market trend")


def test_board_and_fit_pages_lead_with_the_label(client):
    board = client.get("/research/board").get_data(as_text=True)
    assert "building drift 6 mo" in board  # the fixture's served design
    assert '<span class="muted block"><code>' in board
    fit = client.get("/research/fits/m-other").get_data(as_text=True)
    assert 'class="subline design-label">trend quarterly</p>' in fit


def test_hand_written_design_text_is_escaped_without_a_structure(
    site_root, research_file
):
    import json

    from apartments.site.web import create_app

    data = json.loads(research_file.read_text())
    served = next(e for e in data["entries"] if e["id"].startswith("m-test/"))
    served.pop("model")
    research_file.write_text(json.dumps(data))
    client = create_app(site_root, research_data=research_file).test_client()
    html = client.get("/research/fits/m-test/unitdesc-v1/nuts@aaaaaaa").get_data(
        as_text=True
    )
    assert "A test design with &lt;b&gt;bold&lt;/b&gt; claims" in html

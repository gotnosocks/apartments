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
        "trend quarterly · building drift 6 mo · building's own prices: floor · "
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


def test_distinct_structures_get_distinct_labels():
    base = {
        "name": "x",
        "building_walk": True,
        "bedroom_slope": True,
        "trend_knot_months": 3,
        "beta_sd": 0.5,
    }
    variants = [
        {},
        {"learned_feature_groups": ["location"]},
        {"learned_feature_groups": ["spatial"]},
        {"nu_fixed": 5.0},
        {"walk_t": True},
        {"walk_t": True, "walk_nu_fixed": 3.0},
        {"unit_t": True},
        {"unit_t": True, "unit_nu_fixed": 4.0},
        {"noise_by_bedrooms": True},
        {"noise_by_bedrooms": True, "nu_fixed": 5.0},
        {"line_effects": True},
        {"bedroom_time": True},
        {"season_harmonics": 2},
        {"season_harmonics": 2, "season_daily": True},
    ]
    labels = [anatomy.describe({**base, **v}).label for v in variants]
    assert len(set(labels)) == len(labels), labels


def test_board_search_finds_label_words(client):
    html = client.get("/research/board?q=building+drift").get_data(as_text=True)
    assert "m-test" in html

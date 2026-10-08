"""Estimate an unlisted apartment from the served run's prediction kit."""

import datetime as dt
import json
import math
import re
import sqlite3

import pytest
from werkzeug.datastructures import MultiDict

from apartments.site import estimate, estimate_build

GROVE = "the-grove-250-west-19th-street-new_york"
FEATURES = [
    ("bedrooms=0", "bedrooms"),
    ("bedrooms=2", "bedrooms"),
    ("bedrooms=5+", "bedrooms"),
    ("bathrooms=2", "bathrooms"),
    ("bathrooms=4+", "bathrooms"),
    ("bathrooms=half=1", "bathrooms"),
    ("bathrooms=half=unknown", "bathrooms"),
    ("log_sqft_vs_bedroom_median", "size"),
    ("sqft_unknown", "size"),
    ("log_floor", "floor"),
    ("log_floor_above_6", "floor"),
    ("log_floor_above_15", "floor"),
    ("floor_unknown", "floor"),
    ("log_floor_x_no_elevator", "floor"),
    ("elevator=no", "elevator"),
    ("doorman=full_time", "doorman"),
    ("laundry=in_unit", "laundry"),
    ("laundry=unknown", "laundry"),
    ("view_park", "views"),
    ("window_south", "windows"),
    ("label:penthouse", "unit label"),
    ("current_capture_ask", "price_basis"),
    ("description_missing", "description"),
    ("text:renovated", "description"),
    ("looks onto an avenue", "facing"),
    ("looks onto an avenue, floors 1-4", "facing"),
    ("first_listing_of_unit", "relisting"),
    ("log_months_since_last_listing", "relisting"),
    ("line looks onto a street", "line facing"),
    ("line looks onto the rear or a courtyard", "line facing"),
    ("previous_listing_price_change", "previous listing"),
    ("log_previous_listing_repricings", "previous listing"),
    ("outdoor:terrace", "outdoor space"),
    ("rooms beyond bedrooms=3", "rooms beyond bedrooms"),
    ("building era=2010+", "building era"),
    ("West Village", "neighbourhood"),
]


def record(
    draws=4,
    market=None,
    sigma=1e-6,
    unit_scale=1e-6,
    beta=0.0,
    daily=True,
    nu=1e6,
):
    names = [n for n, _ in FEATURES]
    market = math.log(3000) if market is None else market
    return {
        "period": "2026-09-01",
        "features": names,
        "groups": [g for _, g in FEATURES],
        "slopes": ["log_sqft_vs_bedroom_median"],
        "market": [market] * draws,
        "season": {"daily": daily, "coef": [[0.0] * (4 if daily else 12)] * draws},
        "beta": [[beta] * len(names)] * draws,
        "bedroom_time": [[0.0] * 4] * draws,
        "sigma": [[sigma] * 4] * draws,
        "nu": [nu] * draws,
        "unit_scale": [unit_scale] * draws,
        "unit_nu": [5.0] * draws,
        "t_units": True,
    }


def kit(**kw):
    return estimate.Kit.from_record(
        record(**kw), {"1": math.log(700), "2": math.log(1000)}
    )


def flat_building(draws=4, level=0.0):
    return estimate.Building([level] * draws, [0.0] * draws, [[0.0]] * draws, {})


DAY = dt.date(2026, 10, 5)


def test_encode_maps_each_field_to_the_models_columns():
    k = kit()
    form = estimate.Form(
        bedrooms=2,
        full_baths=2,
        half_baths="1",
        square_feet=1100,
        floor=3,
        laundry="in_unit",
        label="penthouse",
        rooms="3",
        facing=["avenue"],
        outdoor=["terrace"],
        views=["park"],
        windows=["south"],
        extras=["renovated"],
    )
    x = estimate.encode(
        form,
        k,
        {
            "building era=2010+": 1.0,
            "West Village": 1.0,
            "elevator=no": 1.0,
            "text:renovated": 1.0,
            "laundry=unknown": 1.0,
            "view_park": 1.0,
        },
    )
    assert x["bedrooms=2"] == 1 and x["bathrooms=2"] == 1 and x["bathrooms=half=1"] == 1
    assert x["log_sqft_vs_bedroom_median"] == pytest.approx(math.log(1100 / 1000))
    assert x["log_floor"] == pytest.approx(math.log(3))
    assert "log_floor_above_6" not in x
    assert x["log_floor_x_no_elevator"] == pytest.approx(
        math.log(3)
    )  # walk-up building
    assert (
        x["laundry=in_unit"] == 1 and "laundry=unknown" not in x
    )  # the form's, not the building's
    assert x["label:penthouse"] == 1 and x["rooms beyond bedrooms=3"] == 1
    assert x["looks onto an avenue"] == 1 and x["looks onto an avenue, floors 1-4"] == 1
    assert (
        x["outdoor:terrace"] == 1
        and x["window_south"] == 1
        and x["text:renovated"] == 1
    )
    # The building's own groups come from its newest listing.
    assert (
        x["building era=2010+"] == 1
        and x["West Village"] == 1
        and x["elevator=no"] == 1
    )
    # A new listing: first of its apartment, at a current ask, with an ad.
    assert x["first_listing_of_unit"] == 1 and x["current_capture_ask"] == 1
    assert "description_missing" not in x and "log_months_since_last_listing" not in x


def test_blank_fields_take_the_not_stated_levels():
    x = estimate.encode(estimate.Form(), kit(), {})
    assert (
        x["sqft_unknown"] == 1 and x["floor_unknown"] == 1 and x["laundry=unknown"] == 1
    )
    assert not any(n.startswith(("bedrooms=", "bathrooms=")) for n in x)
    x = estimate.encode(
        estimate.Form(
            bedrooms=5,
            full_baths=4,
            half_baths="unknown",
            laundry="in_building",
            floor=20,
        ),
        kit(),
        {},
    )
    assert x["bedrooms=5+"] == 1 and x["bathrooms=4+"] == 1
    assert x["bathrooms=half=unknown"] == 1 and "laundry=in_unit" not in x
    assert x["log_floor_above_15"] == pytest.approx(math.log(20 / 15))


def test_form_parsing_drops_invalid_values():
    form = estimate.Form.parse(
        MultiDict(
            [
                ("bedrooms", "9"),
                ("baths", "2"),
                ("sqft", "1,050"),
                ("floor", "-3"),
                ("ask", "$4,500"),
                ("extras", "renovated"),
                ("extras", "<script>"),
                ("facing", "rear"),
            ]
        )
    )
    assert form.bedrooms == 1 and form.full_baths == 2 and form.square_feet == 1050
    assert form.floor is None and form.ask == 4500
    assert form.extras == ["renovated"] and form.facing == ["rear"]


def test_a_certain_kit_gives_its_market_rent():
    k = kit()
    x = estimate.encode(estimate.Form(), k, {})
    out = estimate.score(k, flat_building(), x, 1, DAY, seed="s", ask=3500)
    for key in ("median", "lower_95", "upper_95", "pred_lower_80", "pred_upper_80"):
        assert out[key] == pytest.approx(3000, rel=1e-4)
    assert (
        out["ask_share_below"] == 1.0
        and out["samples"] == 4 * estimate.SAMPLES_PER_DRAW
    )


def test_the_likely_range_is_the_noise_quantiles():
    k = kit(sigma=0.1, draws=50)
    out = estimate.score(k, flat_building(50), {}, 1, DAY, seed="s", samples=400)
    z80 = 1.2815515655446004
    assert out["pred_lower_80"] == pytest.approx(3000 * math.exp(-0.1 * z80), rel=0.01)
    assert out["pred_upper_80"] == pytest.approx(3000 * math.exp(0.1 * z80), rel=0.01)
    assert out["median"] == pytest.approx(3000, rel=1e-4)  # no unit spread
    assert out["estimate"] == out["median"]  # never the mean
    again = estimate.score(k, flat_building(50), {}, 1, DAY, seed="s", samples=400)
    assert again == out  # the same inputs give the same numbers


def test_terms_add_up_on_the_log_scale():
    k = kit(beta=0.1)
    b = flat_building(level=0.2)
    x = {"bedrooms=2": 1.0, "log_sqft_vs_bedroom_median": 0.5}
    total = estimate.totals(k, b, x, 2, DAY)[0]
    assert total == pytest.approx(math.log(3000) + 0.1 * 1.5 + 0.2)
    parts = {p["group"]: p["pct"] for p in estimate.parts(k, b, x, 2)}
    assert parts["bedrooms"] == pytest.approx(100 * math.expm1(0.1))
    assert parts["size"] == pytest.approx(100 * math.expm1(0.05))
    assert parts["building"] == pytest.approx(100 * math.expm1(0.2))


def test_daily_and_monthly_seasons():
    r = record()
    r["season"]["coef"] = [[0.0, 0.0, 0.1, 0.0]] * 4  # cos of the first harmonic
    k = estimate.Kit.from_record(r, {})
    jan1 = estimate.totals(k, flat_building(), {}, 1, dt.date(2026, 1, 1))[0]
    jul2 = estimate.totals(k, flat_building(), {}, 1, dt.date(2026, 7, 2))[0]
    assert jan1 - math.log(3000) == pytest.approx(0.1)
    assert jul2 - math.log(3000) == pytest.approx(-0.1, abs=1e-3)
    r = record(daily=False)
    r["season"]["coef"] = [[0.01 * m for m in range(12)]] * 4
    k = estimate.Kit.from_record(r, {})
    assert estimate.totals(k, flat_building(), {}, 1, DAY)[0] - math.log(
        3000
    ) == pytest.approx(0.09)


def test_sqft_medians_are_recovered_from_the_rows():
    rows = [
        (1.0, 700.0, json.dumps({"log_sqft_vs_bedroom_median": 0.0})),
        (
            1.0,
            770.0,
            json.dumps({"log_sqft_vs_bedroom_median": round(math.log(1.1), 4)}),
        ),
        (
            1.0,
            500.0,
            json.dumps({"log_sqft_vs_bedroom_median": 0.2}),
        ),  # the unit's size
        (1.0, None, json.dumps({"sqft_unknown": 1.0})),
        (6.0, 2000.0, json.dumps({"log_sqft_vs_bedroom_median": 0.0})),
    ]
    medians = estimate.sqft_medians(rows)
    assert medians["1"] == pytest.approx(math.log(700), abs=1e-3)
    assert medians["5+"] == pytest.approx(math.log(2000), abs=1e-3)


def test_a_kit_with_unknown_inputs_gets_no_form(tmp_path):
    r = record()
    r["features"].append("something new")
    r["groups"].append("mystery")
    assert estimate.Kit.from_record(r, {}).unknown_groups() == ["mystery"]


def install_kit(site_root, rec=None):
    """Kit tables written straight into the fixture build (its checks need
    more rows than the fixture has)."""
    path = (site_root / "current" / "site.sqlite").resolve()
    db = sqlite3.connect(path)
    db.execute("DELETE FROM kit")
    db.execute("DELETE FROM kit_buildings")
    db.executemany(
        "INSERT INTO kit VALUES (?,?)",
        [
            ("record", json.dumps(rec or record(sigma=0.05, unit_scale=0.05))),
            ("sqft_median", json.dumps({"1": math.log(700)})),
        ],
    )
    db.execute(
        "INSERT INTO kit_buildings VALUES (?,?,?,?)",
        (GROVE, json.dumps([0.1] * 4), json.dumps([0.0] * 4), json.dumps([[0.0]] * 4)),
    )
    db.commit()
    db.close()


def page(client, url):
    return " ".join(client.get(url).get_data(as_text=True).split())


def test_the_fixture_build_records_why_it_has_no_form(site_root, client):
    info = json.loads((site_root / "current" / "build.json").read_text())
    assert info["stats"]["estimate_form"] == {
        "available": False,
        "reason": "no prediction kit for this run",
    }
    html = page(client, "/estimate")
    assert "not available for this build" in html


def test_estimate_page_scores_an_apartment(site_root, client):
    install_kit(site_root)
    html = page(
        client, f"/estimate?building={GROVE}&bedrooms=1&sqft=650&floor=12&ask=9000"
    )
    assert 'id="result"' in html and "An apartment like this at The Grove" in html
    assert "Typical rent" in html and "Likely ask range" in html
    assert "above the likely range" in html
    assert "market level as of Sep 2026" in html
    assert 'id="floor-caveat"' not in html  # The Grove has 20 floors
    assert "only 3 listings from this building" in html
    assert "What makes up the estimate" in html and "This building" in html


def test_a_floor_above_the_building_is_flagged(site_root, client):
    install_kit(site_root)
    html = page(client, f"/estimate?building={GROVE}&floor=40")
    assert 'id="floor-caveat"' in html and "above the 20 floors" in html


def test_building_search_picks_or_lists(site_root, client):
    install_kit(site_root)
    html = page(client, "/estimate?q=250+west+19&bedrooms=2")
    assert "An apartment like this at The Grove" in html  # one match: chosen
    html = page(client, "/estimate?q=west&bedrooms=2")
    assert "Which building?" in html and 'id="result"' not in html
    assert f"building={GROVE}" in html and "bedrooms=2" in html  # the form is kept
    html = page(client, "/estimate?q=nowhere")
    assert "No building matches" in html


def test_a_build_without_kit_tables_still_serves_the_page(site_root, client):
    path = (site_root / "current" / "site.sqlite").resolve()
    db = sqlite3.connect(path)
    db.execute("DROP TABLE kit")
    db.commit()
    db.close()
    assert "not available for this build" in page(client, "/estimate")


def test_install_refuses_a_kit_of_unknown_inputs(tmp_path):
    kit_dir = tmp_path / "kit"
    kit_dir.mkdir()
    r = record()
    r["features"].append("something new")
    r["groups"].append("mystery")
    (kit_dir / "kit.json").write_text(json.dumps(r))
    import duckdb

    src = tmp_path / "b.json"
    src.write_text(
        json.dumps(
            {
                "building": GROVE,
                "level": [0.0] * 4,
                "bedroom_slope": [0.0] * 4,
                "fslope": [[0.0]] * 4,
            }
        )
    )
    duckdb.connect().execute(
        f"COPY (SELECT * FROM read_json_auto('{src}')) TO '{kit_dir / 'buildings.parquet'}' (FORMAT parquet)"
    )
    files = {
        n: estimate_build._sha256(kit_dir / n)
        for n in ("kit.json", "buildings.parquet")
    }
    (kit_dir / "complete.json").write_text(json.dumps({"files": files}))
    db = sqlite3.connect(":memory:")
    status = estimate_build.install(db, kit_dir, [], {})
    assert not status["available"] and "mystery" in status["reason"]
    assert db.execute("SELECT COUNT(*) FROM kit").fetchone()[0] == 0


def test_find_kit_matches_the_summary(tmp_path):
    for name, sha in (("run-a-1111111", "x"), ("run-a-2222222", "y")):
        d = tmp_path / name
        d.mkdir()
        (d / "complete.json").write_text(
            json.dumps(
                {
                    "version": "frontier-kit-v1",
                    "run": "run-a",
                    "summary_sha256": sha,
                    "created_at": "2026-10-05",
                }
            )
        )
    assert estimate_build.find_kit("run-a", "y", tmp_path).name == "run-a-2222222"
    assert estimate_build.find_kit("run-a", "z", tmp_path) is None
    assert estimate_build.find_kit("run-b", "y", tmp_path) is None


def test_building_pages_link_the_form_when_it_is_available(site_root, client):
    assert "Estimate an apartment in this building" not in page(
        client, f"/buildings/{GROVE}"
    )
    install_kit(site_root)
    html = page(client, f"/buildings/{GROVE}")
    assert f'class="action" href="/estimate?building={GROVE}"' in html


def test_a_building_pick_carries_only_the_forms_keys(site_root, client):
    install_kit(site_root)
    for extra in ("endpoint=x", "_anchor=zz", "_method=POST", "_external=1"):
        r = client.get(f"/estimate?q=west&bedrooms=2&{extra}")
        assert r.status_code == 200, extra
        html = r.get_data(as_text=True)
        assert (
            "bedrooms=2" in html
            and "_external" not in html
            and "http://" not in html.split("Which building?")[1][:2000]
        )


def test_adding_an_ask_leaves_the_estimate_as_it_was(site_root, client):
    install_kit(site_root)
    base = f"/estimate?building={GROVE}&bedrooms=1&sqft=650"

    def figures(html):
        head = html.split('id="result"')[1].split("Likely ask range")
        likely = head[1].split("for 95%")[0]
        return re.findall(r"\$[\d,]+", head[0] + likely)

    plain, asked = page(client, base), page(client, base + "&ask=5200")
    assert len(figures(plain)) == 7  # estimate, its range, the 80% and 95% ranges
    assert figures(plain) == figures(asked) and "Your ask" in asked


def test_the_parts_show_the_season():
    r = record()
    r["season"]["coef"] = [[0.0, 0.0, 0.1, 0.0]] * 4
    k = estimate.Kit.from_record(r, {})
    parts = {
        p["group"]: p["pct"]
        for p in estimate.parts(k, flat_building(), {}, 1, dt.date(2026, 1, 1))
    }
    assert parts["season"] == pytest.approx(100 * math.expm1(0.1))


def check_rows(k, n=24, studio_shift=0.0):
    """Bundle-like rows of the kit's last month whose estimates are the kit's own."""
    rows = []
    for i in range(n):
        beds = 0.0 if i % 2 else 1.0
        log_rent = math.log(3000) + (studio_shift if beds == 0 else 0.0)
        rows.append(
            {
                "audit_id": f"r{i}",
                "period": "2026-09-01",
                "price_at": "2026-09-15T00:00:00+00:00",
                "in_fit": 1,
                "unit_fit_rows": 1,
                "pareto_k": 0.1,
                "building_id": GROVE,
                "bedrooms": beds,
                "inputs": "{}",
                "estimate_median": math.exp(log_rent),
                "pred_lower_80": math.exp(log_rent),
                "pred_upper_80": math.exp(log_rent),
            }
        )
    return rows


def test_the_scoring_check_scores_studios_as_studios():
    r = record()
    r["bedroom_time"] = [[0.2, 0.0, 0.0, 0.0]] * 4  # studios ask 22% more
    k = estimate.Kit.from_record(r, {})
    buildings = {GROVE: flat_building()}
    assert estimate_build.check_scoring(k, buildings, check_rows(k, studio_shift=0.2))[
        "passes"
    ]
    out = estimate_build.check_scoring(k, buildings, check_rows(k, studio_shift=0.0))
    assert not out["passes"] and "differ" in out["reason"]
    few = estimate_build.check_scoring(
        k, buildings, check_rows(k, n=5, studio_shift=0.2)
    )
    assert not few["passes"] and "only 5 rows" in few["reason"]


def test_the_encoding_check_compares_once_listed_apartments():
    k = kit()
    obs = {
        "a": {
            "bedrooms": 2.0,
            "reported_full_bathrooms": 1,
            "reported_half_bathrooms": 0,
            "square_feet": 1000.0,
            "listed_floor": 3,
            "laundry_type": "in_unit",
            "canonical_unit_url": "https://streeteasy.com/building/x/3a",
            "view_exposures": {"park": True},
            "window_exposures": {},
        },
    }
    good = {
        "bedrooms=2": 1.0,
        "log_floor": round(math.log(3), 4),
        "laundry=in_unit": 1.0,
        "view_park": 1.0,
        "log_sqft_vs_bedroom_median": 0.0,
    }
    listing = {"audit_id": "a", "unit_id": "u", "inputs": json.dumps(good)}
    out = estimate_build.check_encoding(k, [listing], obs)
    assert out["passes"] and out["listings"] == 1
    bad = dict(good, **{"laundry=in_unit": 0.0})
    out = estimate_build.check_encoding(k, [dict(listing, inputs=json.dumps(bad))], obs)
    assert not out["passes"] and out["agreement"]["laundry"] == 0
    twice = [listing, dict(listing, audit_id="b")]
    assert (
        estimate_build.check_encoding(k, twice, obs)["listings"] == 0
    )  # listed twice: skipped


def test_home_links_the_form_only_when_it_is_available(site_root, client):
    assert "Estimate an apartment that isn't listed" not in page(client, "/")
    install_kit(site_root)
    assert 'href="/estimate">Estimate an apartment that isn' in page(client, "/")


def test_the_form_says_which_building_facts_it_takes(site_root, client):
    install_kit(site_root)
    html = page(client, f"/estimate?building={GROVE}&bedrooms=1")
    assert (
        'id="form-facts"' in html and "From the building's records and listings" in html
    )
    assert 'name="elevator"' in html and 'name="doorman"' in html
    assert 'id="facts-h"' in html and f'href="/buildings/{GROVE}">listings</a>' in html
    assert 'id="form-facts"' not in page(client, "/estimate")


def test_the_form_can_set_the_elevator_and_doorman():
    k = kit()
    walk_up = {"elevator=no": 1.0}
    form = estimate.Form(floor=5, elevator="yes", doorman="full_time")
    x = estimate.encode(form, k, walk_up)
    assert "elevator=no" not in x and "log_floor_x_no_elevator" not in x
    assert x["doorman=full_time"] == 1
    x = estimate.encode(estimate.Form(floor=5, elevator="no"), k, {})
    assert x["elevator=no"] == 1 and x["log_floor_x_no_elevator"] > 0
    # Left as the building's, they keep it and the seed of older estimates.
    assert estimate.encode(estimate.Form(floor=5), k, walk_up)["elevator=no"] == 1
    assert "elevator" not in estimate.Form().canonical()
    assert "elevator" in estimate.Form(elevator="no").canonical()


def test_line_facing_counts_only_when_the_apartments_own_is_not_given():
    k = kit()
    assert not k.unknown_groups()
    x = estimate.encode(estimate.Form(line="rear"), k, {})
    assert x["line looks onto the rear or a courtyard"] == 1
    x = estimate.encode(estimate.Form(line="rear", facing=["avenue"]), k, {})
    assert not any(n.startswith("line looks") for n in x)
    # A first listing has no previous listing to have been repriced.
    assert not any("previous_listing" in n for n in x)
    assert estimate.Form.parse(MultiDict({"line": "street"})).line == "street"
    assert estimate.Form.parse(MultiDict({"line": "sideways"})).line == ""
    assert "line" not in estimate.Form().canonical()


def test_a_set_elevator_shows_beside_the_buildings(site_root, client):
    install_kit(site_root)
    html = " ".join(
        page(client, f"/estimate?building={GROVE}&bedrooms=1&elevator=no").split()
    )
    assert "(as you set it; its listings say" in html
    assert '<option value="no" selected>' in html


def test_your_ask_says_which_side_of_the_simulated_asks_it_is_on(site_root, client):
    install_kit(site_root)
    base = f"/estimate?building={GROVE}&bedrooms=1&sqft=650&ask="
    low, high = (" ".join(page(client, base + a).split()) for a in ("500", "90000"))
    assert "below the likely range: lower than nearly all simulated asks" in low
    assert "above the likely range: higher than nearly all simulated asks" in high
    assert "higher than 0%" not in low


def test_the_skip_link_and_the_result_take_focus(site_root, client):
    # Fragment navigation focuses only a focusable target (playtest round 4, keyboard).
    install_kit(site_root)
    html = page(client, f"/estimate?building={GROVE}&bedrooms=1")
    assert '<main id="main" class="wrap" tabindex="-1">' in html
    assert 'id="result" tabindex="-1"' in html


def test_the_building_choices_say_enough_to_tell_them_apart(site_root, client):
    install_kit(site_root)
    db = sqlite3.connect(site_root / "current" / "site.sqlite")
    grove = db.execute("SELECT * FROM buildings WHERE id = ?", (GROVE,)).fetchone()
    cols = [r[1] for r in db.execute("PRAGMA table_info(buildings)")]
    twin = dict(zip(cols, grove), id="grove-twin", name=None, bbl="1000000001")
    db.execute(
        f"INSERT INTO buildings ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
        [twin[c] for c in cols],
    )
    db.execute("UPDATE buildings SET bbl = '1000000001' WHERE id = ?", (GROVE,))
    db.commit()
    db.close()
    html = page(client, "/estimate?q=250+west+19")
    assert "Which building?" in html and "listings since" in html
    assert (
        "Same address and tax lot as The Grove, but listed as a separate building"
        in html
    )


def test_the_estimate_says_it_is_a_market_ask_not_a_renewal(site_root, client):
    # Playtest round 4 (tablet): a stabilized tenant compared the estimate with a renewal.
    install_kit(site_root)
    html = page(client, f"/estimate?building={GROVE}&bedrooms=1")
    assert 'id="market-rate"' in html and "Rent Guidelines Board" in html
    assert "not the legal rent of an existing lease" not in html
    html = page(client, f"/estimate?building={GROVE}&bedrooms=1&extras=rent_stabilized")
    assert "not the legal rent of an existing lease" in html


def test_the_estimate_says_first_listings_run_narrow(site_root, client):
    # Playtest round 4 (economist): single-listing under-coverage was only on the model page.
    install_kit(site_root)
    html = page(client, f"/estimate?building={GROVE}&bedrooms=1")
    assert 'id="single-coverage"' in html and "within the 95% ask range" in html
    path = (site_root / "current" / "site.sqlite").resolve()
    db = sqlite3.connect(path)
    stats = json.loads(
        db.execute("SELECT value FROM meta WHERE key='stats'").fetchone()[0]
    )
    del stats["calibration"]["single"]
    db.execute("UPDATE meta SET value=? WHERE key='stats'", (json.dumps(stats),))
    db.commit()
    db.close()
    assert 'id="single-coverage"' not in page(
        client, f"/estimate?building={GROVE}&bedrooms=1"
    )


def test_building_suggestions(site_root, client):
    # Playtest round 4 (keyboard, broker, tablet): no autocomplete in building search.
    install_kit(site_root)
    rows = client.get("/buildings.json?q=grove").get_json()
    assert rows and rows[0]["id"] == GROVE and rows[0]["value"] == "The Grove"
    assert "250 West 19th Street" in rows[0]["label"] and "listings" in rows[0]["label"]
    assert client.get("/buildings.json?q=g").get_json() == []
    assert client.get("/buildings.json?q=%25%25").get_json() == []
    assert len(client.get("/buildings.json?q=st").get_json()) <= 8
    for path in ("/estimate", "/listings", "/buildings", "/estimates"):
        assert 'data-suggest="/buildings.json"' in page(client, path)
    assert 'data-suggest-id="building"' in page(client, "/estimate")

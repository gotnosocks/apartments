import csv
import gzip
import io
import itertools
import json
import re
import sqlite3
from pathlib import Path

import pytest

from apartments.site import charts, web
from apartments.site.web import create_app

GROVE = "the-grove-250-west-19th-street-new_york"


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/listings",
        "/listings?status=current",
        "/listings/a1",
        "/listings/a3",
        "/units/u1",
        "/units/u2",
        "/buildings",
        f"/buildings/{GROVE}",
        "/estimates",
        "/about",
        "/research/model",
        "/quarantined",
        f"/quarantined?building={GROVE}",
        "/listings/q1",
        "/listings/q2",
    ],
)
def test_pages_render(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert response.mimetype == "text/html"
    assert b"NYC Rents" in response.data


def listed(client, query=""):
    """audit ids of the listing links on a /listings page, in order."""
    html = client.get("/listings" + query).get_data(as_text=True)
    return [part.split('"')[0] for part in html.split('href="/listings/')[1:]]


def test_listing_filters(client):
    assert listed(client) == ["a3", "a4", "a2", "a1", "a6", "a5"]  # newest first
    assert listed(client, "?status=current") == ["a3"]
    assert listed(client, "?status=past&beds=0") == ["a6", "a5"]
    assert listed(client, "?beds=2&beds=4") == ["a4"]
    assert listed(client, "?price=below") == ["a2"]
    assert listed(client, "?price=above") == ["a4"]
    assert listed(client, "?min_ask=3000&max_ask=%243%2C500") == ["a3", "a1"]
    assert listed(client, "?from=2019&to=2021") == ["a2", "a1"]
    assert listed(client, "?q=grove") == ["a3", "a4", "a2", "a1"]
    assert listed(client, "?q=23rd") == ["a6", "a5"]
    assert listed(client, "?q=11-c") == ["a3"]  # exact unit label
    assert listed(client, "?sort=ask") == ["a5", "a6", "a2", "a1", "a3", "a4"]
    assert listed(client, "?sort=diff_pct&order=desc")[0] == "a4"


def test_invalid_parameters_fall_back_to_defaults(client):
    default = listed(client)
    for query in (
        "?page=abc&per=7",
        "?sort=ask;DROP TABLE listings&order=sideways",
        "?beds=9&status=nope&price=cheap",
        "?min_ask=-5&max_ask=nan&from=12&to=abcd",
        "?q=%25%25%25_",
    ):
        response = client.get("/listings" + query)
        assert response.status_code == 200
        if "q=" not in query:
            assert listed(client, query) == default
    assert listed(client, "?q=%25") == []  # a literal %, not a wildcard


def test_pagination(client):
    html = client.get("/listings?per=25&page=99").get_data(as_text=True)
    assert "Page" not in html  # one page only; out-of-range pages clamp


def test_csv_export_follows_the_filters(client):
    response = client.get("/listings.csv?q=grove&sort=ask")
    assert response.status_code == 200 and response.mimetype == "text/csv"
    rows = list(csv.DictReader(io.StringIO(response.get_data(as_text=True))))
    assert [r["audit_id"] for r in rows] == ["a2", "a1", "a3", "a4"]
    assert rows[0]["price_band"] == "below" and float(rows[0]["ask"]) == 2600.0
    assert rows[0]["neighbourhood"] == "Chelsea"


def test_listing_page_explains_the_estimate(client):
    html = client.get("/listings/a3").get_data(as_text=True)
    assert "Less reliable estimate" in html
    assert (
        "the unit&#39;s 2 other listings" in html or "unit's 2 other listings" in html
    )
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html  # data is escaped
    assert "<script>alert(1)</script>" not in html
    assert "renovated" in html and "penthouse" in html
    assert "At their reference level, adding nothing: Bedrooms" in html
    single = client.get("/listings/a4").get_data(as_text=True)
    assert "only listing in the model fit" in single and "Above typical" in single
    held = client.get("/listings/a2").get_data(as_text=True)
    assert "held out of the model fit" in held


def test_listing_diagnostics_are_folded_away_and_glossed(client):
    html = " ".join(client.get("/listings/a3").get_data(as_text=True).split())
    assert (
        "that shortcut is unstable (its" in html
        and 'href="/research/glossary#pareto-k"' in html
    )
    assert '<details class="table-view" id="model-details">' in html
    assert "<summary>Model details, for statisticians</summary>" in html
    assert "(above 0.7, so less reliable)" in html
    reliable = " ".join(client.get("/listings/a4").get_data(as_text=True).split())
    assert "Less reliable estimate" not in reliable
    assert "the fit reweighted as if it had not seen this ask" in reliable
    assert "(below 0.7: the reweighting is reliable)" in reliable


def test_building_page(client):
    html = client.get(f"/buildings/{GROVE}").get_data(as_text=True)
    assert "The Grove" in html and "250 West 19th Street" in html
    assert "+10%" in html and "Built" in html and "1986" in html
    assert "Floors" in html
    assert 'data-chart="points"' in html
    current = client.get(f"/buildings/{GROVE}?status=current").get_data(as_text=True)
    assert current.count('href="/listings/') == 1


def test_a_short_units_table_shows_whole_with_its_count(client):
    # Playtest round 5 (renewer): a capped scroll box hid most units unnoticed.
    html = client.get(f"/buildings/{GROVE}").get_data(as_text=True)
    units = html.split("<h2>Units", 1)[1].split("</section>", 1)[0]
    n = units.count('href="/units/')
    assert n and f'<span class="muted">· {n}</span>' in units
    assert "table-wrap tall" not in units and 'id="units-scroll"' not in units


def test_buildings_index_search_and_sort(client):
    html = client.get("/buildings?q=west+23").get_data(as_text=True)
    assert "134 West 23rd Street" in html and "The Grove" not in html
    html = client.get("/buildings?sort=level&order=desc").get_data(as_text=True)
    assert html.index("The Grove") < html.index("134 West 23rd Street")


def test_not_found(client):
    assert client.get("/listings/zzz").status_code == 404
    assert client.get("/units/zzz").status_code == 404
    assert client.get("/buildings/zzz").status_code == 404
    response = client.get("/no-such-page")
    assert response.status_code == 404 and b"Not found" in response.data


def test_security_and_cache_headers(client):
    response = client.get("/")
    csp = response.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp and "script-src 'self'" in csp
    assert "unsafe-inline" not in csp
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Cache-Control"] == "no-cache"
    etag = response.headers["ETag"]
    assert client.get("/", headers={"If-None-Match": etag}).status_code == 304
    static = client.get("/static/site.css?v=1")
    assert "max-age=31536000" in static.headers["Cache-Control"]
    static.close()


def test_untrusted_host_is_refused(client):
    assert client.get("/", headers={"Host": "evil.example"}).status_code == 400
    assert (
        client.get("/", headers={"Host": "thelio.example.ts.net:8600"}).status_code
        == 200
    )


def test_gzip_when_accepted(client):
    response = client.get("/listings", headers={"Accept-Encoding": "gzip"})
    assert response.headers["Content-Encoding"] == "gzip"
    assert b"NYC Rents" in gzip.decompress(response.data)


def test_healthz(client):
    response = client.get("/healthz")
    body = response.get_json()
    assert response.status_code == 200 and body["status"] == "ok"
    assert body["listings"] == 6 and body["run"] == "m-test-run"
    assert response.headers["Cache-Control"] == "no-store"


def test_no_published_build_is_503(tmp_path):
    app = create_app(tmp_path / "empty")
    client = app.test_client()
    response = client.get("/")
    assert response.status_code == 503 and b"Not available yet" in response.data
    assert client.get("/healthz").status_code == 503


def test_a_new_publish_is_served_without_restart(client, site_root, bundle):
    from apartments.site import build

    first = client.get("/healthz").get_json()["build"]
    build.build(bundle, site_root)
    assert client.get("/healthz").get_json()["build"] != first


def test_robots(client):
    assert client.get("/robots.txt").get_data(as_text=True).endswith("Disallow: /\n")


def test_nice_ticks_cover_the_range():
    ticks = charts.nice_ticks(2830.0, 5310.0)
    assert ticks[0] <= 2830 and ticks[-1] >= 5310
    steps = {round(b - a, 6) for a, b in itertools.pairwise(ticks)}
    assert len(steps) == 1 and steps.pop() in (500.0, 1000.0)


def test_chart_data_block_cannot_close_its_script():
    figure = charts.residual_scatter(
        [{"period": "2020-01-01", "residual_pct": 0.1, "title": "</script><b>x"}],
        label="t",
    )
    assert "</script><b>" not in str(figure).split('class="chart-data">')[1][:-20]


def test_money_and_percent_formatting():
    assert charts.usd(-885.4, signed=True) == "−$885"
    assert charts.usd(1200) == "$1,200"
    assert charts.pct(-19.1, digits=1) == "−19.1%"
    assert charts.pct(0.0) == "0%"


@pytest.mark.parametrize("sort", sorted(web.SORTS))
@pytest.mark.parametrize("order", ["asc", "desc"])
@pytest.mark.parametrize("extra", [{}, {"page": "3"}])
def test_every_sort_pages_through_an_index(site_root, sort, order, extra):
    """No whole-table sort: unfiltered, the page's ids come off an index in
    either order (a filtered page sorts only its matching ids)."""
    from werkzeug.datastructures import MultiDict

    filters = web.Filters(MultiDict({"sort": sort, "order": order, **extra}))
    sql, params = web.page_query(filters)
    db = sqlite3.connect(site_root / "current" / "site.sqlite")
    plan = " | ".join(r[3] for r in db.execute("EXPLAIN QUERY PLAN " + sql, params))
    db.close()
    ids_part = plan.split("SCAN page")[0]
    assert "TEMP B-TREE" not in ids_part, plan


def test_model_page_without_a_calibration_group(client, site_root):
    """An all-rows fit has no held-out rows; /about must still render."""
    path = (site_root / "current" / "site.sqlite").resolve()
    db = sqlite3.connect(path)
    stats = json.loads(
        db.execute("SELECT value FROM meta WHERE key='stats'").fetchone()[0]
    )
    del stats["calibration"]["heldout"]
    db.execute("UPDATE meta SET value=? WHERE key='stats'", (json.dumps(stats),))
    db.commit()
    db.close()
    html = client.get("/about").get_data(as_text=True)
    assert "only listing in the fit" in html and "Held out of the fit" not in html
    assert client.get("/listings/a4").status_code == 200


def test_chart_data_block_has_no_angle_brackets():
    figure = str(
        charts.residual_scatter(
            [{"period": "2020-01-01", "residual_pct": 0.1, "title": "<!-- </script>"}],
            label="t",
        )
    )
    block = figure.split('class="chart-data">')[1].split("</script>")[0]
    assert "<" not in block and "\\u003c!--" in block


def test_unit_page_links_to_streeteasy(client):
    html = client.get("/units/u1").get_data(as_text=True)
    unit = f"https://streeteasy.com/building/{GROVE}/11-C"
    assert f'href="{unit}"' in html and "View this unit on StreetEasy" in html
    # each listing's own StreetEasy ad, opened safely in a new tab
    for listing_id in ("1000", "2000", "3000"):
        assert f'href="https://streeteasy.com/rental/{listing_id}"' in html
    assert html.count('rel="noopener noreferrer" target="_blank"') == 4


def test_model_page_describes_the_designs_terms(client, site_root):
    """The building bullet lists the building terms the design has; the sampler
    and the k threshold are shown readably."""
    html = client.get("/about").get_data(as_text=True)
    assert (
        "<strong>building</strong>: its level against a building with the same listed features;"
        in html
    )
    assert "Pareto k above 0.7)" in html
    assert "NUTS (NumPyro) on" in client.get("/research/model").get_data(as_text=True)
    db = sqlite3.connect((site_root / "current" / "site.sqlite").resolve())
    position = db.execute("SELECT max(position) FROM terms").fetchone()[0]
    for i, name in enumerate(["building_drift", "building_bedroom_premium"], 1):
        db.execute(
            "INSERT INTO terms VALUES (?,?,?,?)", (position + i, name, name, "text")
        )
    provenance = json.loads(
        db.execute("SELECT value FROM meta WHERE key='provenance'").fetchone()[0]
    )
    provenance["sampler"] = "gibbs"
    provenance["estimate_pareto_k"]["threshold"] = 0.6752383441917945
    db.execute(
        "UPDATE meta SET value=? WHERE key='provenance'", (json.dumps(provenance),)
    )
    db.commit()
    db.close()
    html = client.get("/about").get_data(as_text=True)
    assert (
        "<strong>building</strong>: its level against a building with the same listed"
        " features, how that level has moved over time and its own premium or discount for larger"
        " apartments;" in html
    )
    assert "Pareto k above 0.675)" in html
    research = client.get("/research/model").get_data(as_text=True)
    assert "Custom Gibbs sampler on" in research


def test_quarantined_listings_are_shown_with_their_reason(client):
    index = client.get("/").get_data(as_text=True)
    assert "2 more listings are" in index and 'href="/quarantined"' in index
    page = client.get("/quarantined").get_data(as_text=True)
    assert "A ground-floor retail space." in page and "Not a home" in page
    assert "Placed elsewhere" in page
    listing = client.get("/listings/q1").get_data(as_text=True)
    assert "Quarantined: no estimate" in listing
    assert "ground floor retail space" in listing  # the ad's own words
    assert "/rental/91" in listing
    office = client.get("/listings/q2").get_data(as_text=True)
    assert "MapPLUTO: office (O6)." in office
    building = client.get(f"/buildings/{GROVE}").get_data(as_text=True)
    assert 'id="quarantined"' in building and "/listings/q1" in building
    # Quarantined listings are not listings: no estimate, not in the search.
    assert "q1" not in [a for a in listed(client)]


def test_a_page_with_only_quarantined_listings_redirects_to_them(client):
    response = client.get("/buildings/103-8-avenue-new_york")
    assert response.status_code == 302
    assert response.headers["Location"].endswith(
        "/quarantined?building=103-8-avenue-new_york"
    )
    page = client.get("/quarantined?building=103-8-avenue-new_york").get_data(
        as_text=True
    )
    assert "no building page" in page
    assert client.get("/quarantined?building=nowhere").status_code == 404
    assert client.get("/units/q-q2").status_code == 302


def test_a_build_without_the_quarantined_table_still_renders(client, site_root):
    # Builds before schema 2 have no quarantined table (a deploy can land first).
    db = sqlite3.connect(site_root / "current" / "site.sqlite")
    db.execute("DROP TABLE quarantined")
    db.commit()
    db.close()
    for path in ("/", "/quarantined", f"/buildings/{GROVE}", "/units/u1"):
        assert client.get(path).status_code == 200, path
    assert client.get("/listings/q1").status_code == 404


def test_home_page_joins_both_sections(client):
    html = client.get("/").get_data(as_text=True)
    assert 'href="/estimates"' in html and 'href="/research/model"' in html
    # the served model's place on the board, from the research data
    flat = " ".join(html.split())
    assert "Predicts asks it has not seen better than the simplest baseline" in flat
    assert "+5,221 ± 120 in a log-score" in flat
    assert "12.4 minutes on Test GPU" in html
    # newest change first; titles are escaped
    assert html.index("Newest &lt;b&gt;change&lt;/b&gt;") < html.index("Serve m-test")
    assert "Model switch" in html and "PR #97" in html


def test_section_navigation(client):
    estimates = client.get("/listings").get_data(as_text=True)
    assert '<nav class="wrap" aria-label="Estimates">' in estimates
    assert 'href="/estimates" aria-current="true"' in estimates
    research = client.get("/research/model").get_data(as_text=True)
    assert '<nav class="wrap" aria-label="Research">' in research
    assert 'href="/research" aria-current="true"' in research
    assert 'aria-label="Estimates">' not in client.get("/").get_data(as_text=True)
    assert (
        client.get("/model").status_code == 404
    )  # moved to /about and /research/model


def test_research_model_page(client):
    html = client.get("/research/model").get_data(as_text=True)
    assert "published by hand" in html  # the fixture bundle is not the repo's selection
    assert "+5,221.3 ± 120.4 over the" in html and "−12.5" not in html
    assert "-12.5" not in html  # the retired PyMC reference comparison
    assert "On the frontier</dt><dd>yes, and the best fit on its hardware" in html
    assert "Convergence gate</dt><dd>passes" in html


def test_research_model_page_shows_the_selection_and_decision(
    tmp_path, bundle, research_file
):
    from apartments.site import build

    selection = tmp_path / "selection.json"
    selection.write_text(
        json.dumps(
            {
                "summary_manifest_sha256": build.sha256(bundle / "complete.json"),
                "selected_by": "rentfrontier.autoselect, 2026-10-01",
                "selection_reason": "Chosen because it clearly beats the incumbent.",
            }
        )
    )
    root = tmp_path / "selected"
    build.build(bundle, root, selection=selection)
    data = json.loads(research_file.read_text())
    data["autoselect"] = {
        "action": "keep",
        "reason": "The served fit is still the best: the incumbent ranks first.",
        "checked": [
            {
                "run": "m-other-run",
                "psis": -3.2,
                "psis_pm": 4.0,
                "heldout": None,
                "elegance": -1,
                "refused": "tied and not faster",
            },
        ],
        "pending_judgements": [["m-new/unitdesc-v1", "m-test/unitdesc-v1"]],
    }
    research_file.write_text(json.dumps(data))
    app = create_app(root, research_data=research_file)
    html = app.test_client().get("/research/model").get_data(as_text=True)
    # "The incumbent" names a different model in each reason, so each says which.
    assert "Chosen because it clearly beats the model it replaced." in html
    assert "Chosen by rentfrontier.autoselect, 2026-10-01." in html
    assert "The served fit is still the best: this model ranks first." in html
    assert "<code>m-other-run</code>" in html and "tied and not faster" in html
    assert "<td>less elegant</td>" in html  # the check's elegance judgement
    assert (
        "<code>m-new/unitdesc-v1</code> against <code>m-test/unitdesc-v1</code>" in html
    )
    assert "more elegant than 1" in html and "#elegance" in html
    assert "Effective parameters</dt><dd>413" in html
    # a check without scores (the incumbent could not be paired) and an
    # entry whose PSIS-LOO has no paired delta still render
    data["autoselect"]["checked"].append({"run": "m-bare-run"})
    served = next(e for e in data["entries"] if e["id"].startswith("m-test/"))
    served["psis"] = {"delta": None, "elpd": 1.0}
    research_file.write_text(json.dumps(data))
    bare = app.test_client().get("/research/model")
    assert bare.status_code == 200 and "<code>m-bare-run</code>" in bare.get_data(
        as_text=True
    )


def test_pages_render_without_research_data(site_root, tmp_path):
    app = create_app(site_root, research_data=tmp_path / "missing.json")
    client = app.test_client()
    for path in ("/", "/research/model", "/estimates"):
        assert client.get(path).status_code == 200, path
    assert "Latest changes" not in client.get("/").get_data(as_text=True)


def test_research_data_reloads_when_the_build_changes(research_file):
    from apartments.site.research import Research

    research = Research(research_file)
    first = research.load()
    assert research.load() is first  # cached
    data = dict(first, generated_at="2026-10-01T12:00:00+00:00")
    research_file.write_text(json.dumps(data) + " ")
    assert research.load()["generated_at"] == "2026-10-01T12:00:00+00:00"
    research_file.write_text("{broken")
    assert research.load()["generated_at"] == "2026-10-01T12:00:00+00:00"


def test_older_builds_fall_back_to_the_repository_selection(
    client, site_root, bundle, tmp_path, monkeypatch
):
    """A build from before the selection was recorded shows the repository's
    selection when it names the published bundle."""
    from apartments.site import build

    db = sqlite3.connect((site_root / "current" / "site.sqlite").resolve())
    db.execute("DELETE FROM meta WHERE key='selection'")
    db.commit()
    db.close()
    selection = tmp_path / "selection.json"
    selection.write_text(
        json.dumps(
            {
                "summary_manifest_sha256": build.sha256(bundle / "complete.json"),
                "selected_by": "rentfrontier.autoselect",
                "selection_reason": "The repository's own reason.",
            }
        )
    )
    monkeypatch.setattr(web, "SELECTION", selection)
    html = client.get("/research/model").get_data(as_text=True)
    assert "The repository&#39;s own reason." in html
    assert "Chosen by</dt><dd>the automatic selection rule" in client.get("/").get_data(
        as_text=True
    )


def test_research_helpers(research_file):
    from apartments.site import research

    data = json.loads(research_file.read_text())
    assert research.is_subset("m7-nb-facing-v1-rows-abc-gibbs-2060-nb-tune35")
    assert not research.is_subset("m5-nocurves-tunits-unitfacing-v5-rows-f74db76")
    assert research.hardware_classes(data) == ["thelio RTX 2060 SUPER", "thelio CPU"]
    assert research.snapshot_days(data) == ["2026-09-30", "2026-09-25"]
    assert research.snapshot_on(data, "2026-09-27")["at"].startswith("2026-09-25")
    assert research.snapshot_on(data, None)["at"].startswith("2026-09-30")
    assert research.snapshot_on(data, "2026-09-01") is None
    # the mean-only baseline is far below the rest: the floor leaves it out
    assert research.outlier_floor([-72000.0, 4100.0, 5000.0, 5221.0, 5300.0]) == 4100.0
    assert research.outlier_floor([4100.0, 5000.0, 5221.0, 5300.0]) is None
    assert research.outlier_floor([1.0, 2.0]) is None


def test_a_failing_exploration_fit_is_marked_failing(research_file):
    """The gate applies to every tier (Ben, 2026-10-05): an exploration fit that
    fails it is off the frontier line and marked failing, not other."""
    from apartments.site import research

    data = json.loads(research_file.read_text())
    for e in data["entries"]:
        if e["id"] == "m-other":
            e["passes_checks"] = False
            e["tier"] = {"name": "exploration", "draws": 600}
    view = research.frontier_view(data, "thelio RTX 2060 SUPER", None, "m-test-run")
    kinds = {f["entry"]["id"]: f["kind"] for f in view["fits"]}
    assert kinds["m-other"] == "failing"


def test_frontier_view_marks_and_as_of(research_file):
    from apartments.site import research

    data = json.loads(research_file.read_text())
    gpu = "thelio RTX 2060 SUPER"
    view = research.frontier_view(data, gpu, None, "m-test-run")
    kinds = {f["entry"]["id"]: f["kind"] for f in view["fits"]}
    assert kinds == {
        "m-test/unitdesc-v1/nuts@aaaaaaa": "served",
        "m-other": "other",
        "m-failing": "failing",
        "L0-mean": "frontier",
    }
    assert view["hidden_subsets"] == 1
    assert [f["entry"]["id"] for f in view["frontier"]] == [
        "m-test/unitdesc-v1/nuts@aaaaaaa",
        "L0-mean",
    ]
    shown = research.frontier_view(data, gpu, None, "m-test-run", subsets=True)
    subset = next(f for f in shown["fits"] if f["kind"] == "subset")
    assert subset["why_not"] == "a subset fit, for exploration only"
    # on 2026-09-27 the served fit had not landed; m-other was on the frontier
    earlier = research.frontier_view(data, gpu, "2026-09-27", "m-test-run")
    kinds = {f["entry"]["id"]: f["kind"] for f in earlier["fits"]}
    assert "m-test/unitdesc-v1/nuts@aaaaaaa" not in kinds
    assert kinds["m-other"] == "frontier"


def test_frontier_page(client):
    html = client.get("/research").get_data(as_text=True)
    assert "Fit time on the RTX 2060, full dataset (minutes)" in html
    # Ben's window, in words; the 2-hour line is drawn only when fits reach it
    assert "within 2 hours" in html and "within 30 minutes" in html
    assert "2-hour limit for a full fit" not in html
    assert 'class="fit served"' in html and 'class="fit failing"' in html
    # the baseline is drawn at the floor, and says so
    assert "below the chart" in html
    assert "1 subset fit hidden." in html
    assert "<code>m-other</code>" in html  # in the table of every fit
    rated = client.get("/research?subsets=1&range=full").get_data(as_text=True)
    assert "below the chart" not in rated
    assert 'class="fit subset"' not in rated  # unscored subsets have no dot
    cpu = client.get("/research?hardware=thelio+CPU").get_data(as_text=True)
    assert "Fit time on thelio CPU, full dataset (minutes)" in cpu
    assert "within 2 hours" not in cpu
    odd = client.get("/research?hardware=nope&as_of=x&range=zzz")
    assert odd.status_code == 200
    past = client.get("/research?as_of=2026-09-25").get_data(as_text=True)
    assert "On the frontier at the end of 2026-09-25" in past
    assert 'class="fit served"' not in past


def test_frontier_page_needs_research_data(site_root, tmp_path):
    app = create_app(site_root, research_data=tmp_path / "missing.json")
    assert app.test_client().get("/research").status_code == 503


def test_fit_scatter_marks_and_legend():
    figure = str(
        charts.fit_scatter(
            [
                {"x": 10, "y": 5000, "kind": "frontier", "title": "a"},
                {"x": 20, "y": -70000, "kind": "other", "title": "b"},
                {"x": 25, "y": 5200, "kind": "served", "title": "c"},
            ],
            label="t",
            x_title="minutes",
            y_title="delta",
            x_format=str,
            y_format=str,
            y_floor=5000,
            x_line=(30, "target"),
        )
    )
    legend = figure.split('<div class="legend">')[1].split("</div>")[0]
    assert legend.index("Served model") < legend.index("On the frontier")
    assert "Fails the convergence checks" not in legend
    assert figure.count('class="fit ') == 3 and "target" in figure
    assert "drawn at its floor" in figure


def test_fit_scatter_zooms_to_a_box():
    points = [
        {"x": 10, "y": 5000, "kind": "frontier", "title": "a"},
        {"x": 20, "y": -70000, "kind": "other", "title": "b"},
        {"x": 25, "y": 5200, "kind": "served", "title": "c"},
    ]
    kw = {
        "label": "t",
        "x_title": "m",
        "y_title": "d",
        "x_format": str,
        "y_format": str,
    }
    figure = str(
        charts.fit_scatter(
            points, x_range=(5, 30), y_range=(4900, 5300), zoom="f", y_floor=-1, **kw
        )
    )
    # the fit outside the box is left off; the axes span the box exactly
    assert figure.count('class="fit ') == 2 and "drawn at its floor" not in figure
    # the Chart.js spec carries every fit and the box, for fitchart.js
    spec = json.loads(figure.split('class="chart-spec">')[1].split("</script>")[0])
    assert spec["zoom"] == "f" and spec["range"] == [5, 30, 4900, 5300]
    assert len(spec["points"]) == len(points)
    ticks = [float(t) for t in re.findall(r'text-anchor="end">([-\d.]+)<', figure)]
    assert ticks and all(4900 <= t <= 5300 for t in ticks)
    assert "No fit falls inside" in str(
        charts.fit_scatter(points, x_range=(100, 200), **kw)
    )
    assert "chart-spec" not in str(charts.fit_scatter(points, **kw))
    # an empty box still carries the whole chart, so Chart.js can zoom out
    empty = str(charts.fit_scatter(points, x_range=(100, 200), zoom="f", **kw))
    assert "No fit falls inside" in empty and '"range":[100,200,null,null]' in empty


def test_review_fixes_on_research_model_and_home(client, research_file):
    data = json.loads(research_file.read_text())
    # a model switch and its merge land at the same time: the switch shows first
    data["milestones"] = [
        {"kind": "pr", "at": "2026-10-01T03:00:00+00:00", "pr": 92, "title": "PR"},
        {"kind": "selection", "at": "2026-10-01T03:00:00+00:00", "title": "Switch"},
    ] + [
        {"kind": "pr", "at": f"2026-10-01T0{h}:00:00+00:00", "pr": h, "title": f"t{h}"}
        for h in range(4, 9)
    ]
    served = next(e for e in data["entries"] if e["id"].startswith("m-test"))
    served["psis"].pop("validation")
    served["splits"]["rows"]["delta_se"] = None
    research_file.write_text(json.dumps(data))
    home = client.get("/").get_data(as_text=True)
    assert "Model switch" in home
    html = client.get("/research/model").get_data(as_text=True)
    assert "held-out listings the" not in " ".join(html.split())
    assert html.count("<dt>Convergence gate</dt>") == 1
    # published by hand: no claim that the rule picked it
    assert "A rule picks it" not in html


def test_board_filters_sorts_and_links(client):
    html = client.get("/research/board").get_data(as_text=True)
    # most accurate first; the subset fit is hidden; the CPU fit is listed
    assert html.index("<code>m-test/") < html.index("<code>m-failing</code>")
    assert "m-subset" not in html and "<code>m-cpu</code>" in html
    assert 'href="/research/fits/m-other"' in html
    assert "beaten by the served fit" in html  # the board's note
    # no fit in this research data is confirmed servable (the served one has no
    # why_not_served), so "only servable" lists none
    servable = client.get("/research/board?servable=1").get_data(as_text=True)
    assert "0</strong> of 6 fits" in servable
    numpyro = client.get("/research/board?line=numpyro").get_data(as_text=True)
    assert "<code>m-test/" not in numpyro and "<code>m-other</code>" in numpyro
    fastest = client.get("/research/board?sort=time").get_data(as_text=True)
    assert fastest.index("<code>L0-mean</code>") < fastest.index("<code>m-test/")
    searched = client.get("/research/board?q=failing").get_data(as_text=True)
    assert "1</strong> of 6 fits" in searched
    with_subsets = client.get("/research/board?subsets=1").get_data(as_text=True)
    assert "no: a subset fit, for exploration only" in with_subsets
    odd = client.get("/research/board?sort=zzz&order=x&hardware=nope&line=nope")
    assert odd.status_code == 200


def test_fit_page(client):
    key = "m-test/unitdesc-v1/nuts@aaaaaaa"
    html = client.get(f"/research/fits/{key}").get_data(as_text=True)
    # this research data has no why_not_served for the served fit
    assert "Not known yet" in html
    # led by what the design does (its recorded structure), not the hand-written text
    assert 'class="subline design-label">' in html
    assert "Serves the app (Ben)." in html
    assert "78.6%" in html and "76.9–80.2%" in html  # variance share
    assert "1.004" in html and "612" in html  # split diagnostics
    other = client.get("/research/fits/m-other").get_data(as_text=True)
    assert "No: it was fit with no data rules" in other
    assert "Where the variation" not in other  # no variance recorded
    assert client.get("/research/fits/nothing-here").status_code == 404


def test_history_page(client):
    html = client.get("/research/history").get_data(as_text=True)
    assert "The best fit's accuracy over time" in html
    assert html.count('class="line s1"') >= 1
    # compute by model line: one series per line, in the fixed order
    legend = html.split("Hours of fitting by model line")[1]
    assert legend.index("Custom samplers (JAX)") < legend.index("NumPyro NUTS")
    assert (
        'href=\\"/research/fits/m-other\\"' in html or "/research/fits/m-other" in html
    )
    assert "Model switch" in html and "PR #97" in html
    assert client.get("/research/history?hardware=thelio+CPU").status_code == 200


def test_history_helpers(research_file):
    from apartments.site import research

    data = json.loads(research_file.read_text())
    assert research.best_over_time(data, "thelio RTX 2060 SUPER") == []  # no deltas
    data["snapshots"][0]["by_class"]["thelio RTX 2060 SUPER"]["best_delta"] = 4100.0
    assert research.best_over_time(data, "thelio RTX 2060 SUPER") == [
        ("2026-09-25T08:00:00+00:00", 4100.0)
    ]
    lines = research.compute_by_line(data)
    assert [s["name"] for s in lines][:2] == ["Custom samplers (JAX)", "NumPyro NUTS"]
    jax = lines[0]["points"]
    assert jax[-1][1] == pytest.approx(745.0 / 3600)


def test_time_axes_and_zero_floor():
    frame = charts.Frame(
        ["2026-09-25T08:00:00+00:00", "2026-10-01T02:00:00+00:00"],
        [3.0, 30.0],
        zero=True,
        clamp_zero=True,
    )
    assert frame.ticks[0] == 0  # fit times never go below zero
    labels = [label for _, label in frame.year_ticks()]
    assert labels[0] == "Sep 26" and "Oct 1" in labels
    long = charts.Frame(["2015-01-01", "2026-09-01"], [1.0, 2.0])
    assert next(label for _, label in long.year_ticks()) == "2016"
    months = charts.Frame(["2026-01-15", "2026-09-01"], [1.0, 2.0])
    assert next(label for _, label in months.year_ticks()) == "Feb 2026"


def test_serve_status_without_the_dashboards_reason():
    """Before the research data carries `why_not_served`, a fit that fails the
    checks is still not servable, and nothing else is claimed."""
    from apartments.site.research import serve_status

    passing = {"passes_checks": True, "splits": {"rows": {"run": "r"}}}
    failing = {"passes_checks": False, "splits": {"rows": {"run": "r"}}}
    assert serve_status(passing) == ("unknown", None)
    assert serve_status(failing) == ("no", "it fails the convergence gate")
    assert serve_status(dict(passing, why_not_served=None)) == ("yes", None)
    assert serve_status(dict(passing, why_not_served="old rules")) == (
        "no",
        "old rules",
    )
    subset = {"passes_checks": True, "splits": {"rows": {"run": "m-nb-tune35"}}}
    assert serve_status(subset) == ("no", "a subset fit, for exploration only")


def test_frontier_page_never_calls_an_unknown_fit_servable(client):
    html = client.get("/research").get_data(as_text=True)
    # the served entry has no why_not_served in this research data
    assert "not known yet" in html
    assert "no: it fails the convergence gate" in html  # m-failing's own reason
    assert html.count("<td>yes</td>") == 0


def test_frontier_page_with_an_empty_board(site_root, research_file):
    research_file.write_text(json.dumps({"entries": [], "snapshots": []}))
    app = create_app(site_root, research_data=research_file)
    assert app.test_client().get("/research").status_code == 503


def test_fit_page_says_yes_only_with_the_dashboards_reason(client, research_file):
    data = json.loads(research_file.read_text())
    served = next(e for e in data["entries"] if e["id"].startswith("m-test"))
    served["why_not_served"] = None
    research_file.write_text(json.dumps(data))
    key = "m-test/unitdesc-v1/nuts@aaaaaaa"
    html = client.get(f"/research/fits/{key}").get_data(as_text=True)
    assert "Yes: it passes every rule the automatic selection applies." in html
    assert "It is the served model." in html
    failing = client.get("/research/fits/m-failing").get_data(as_text=True)
    assert "No: it fails the convergence gate." in failing


def test_board_review_fixes(client, research_file):
    data = json.loads(research_file.read_text())
    served = next(e for e in data["entries"] if e["id"].startswith("m-test"))
    served["why_not_served"] = None
    other = next(e for e in data["entries"] if e["id"] == "m-other")
    other["psis"]["delta_se"] = float("nan")
    other["psis"]["elpd"] = 54570.8
    research_file.write_text(json.dumps(data).replace("NaN", "NaN"))
    servable = client.get("/research/board?servable=1").get_data(as_text=True)
    assert "1</strong> of 6 fits" in servable and "<code>m-test/" in servable
    board = client.get("/research/board").get_data(as_text=True)
    assert "± nan" not in board
    # time sorts fastest first; its link says so
    assert 'href="/research/board?sort=time"' in board
    assert "sort=complexity" not in board and "Complexity" not in board
    assert "less elegant than 1" in board
    assert 'href="/research/board?sort=params"' in board and ">413<" in board
    assert 'href="/research/board?sort=landed"' in board
    assert "best on its hardware" in board
    fit = client.get("/research/fits/m-other").get_data(as_text=True)
    assert "± nan" not in fit
    assert "the log of the probability the fit gives" in fit


def test_history_review_fixes(client, site_root, research_file):
    html = client.get("/research/history").get_data(as_text=True)
    assert '<th scope="col">Landed</th>' in html  # the fit-time chart's table view
    assert "No fit on thelio RTX 2060 SUPER has a PSIS-LOO score yet." in html
    research_file.write_text(json.dumps({"entries": [], "snapshots": []}))
    assert client.get("/research/history").status_code == 503


def test_axis_review_fixes():
    assert charts.signed(0) == "0" and charts.signed(1500) == "+1,500"
    assert charts.signed(-500) == "−500"
    # monthly periods over a short span keep month ticks, not days
    monthly = charts.Frame(["2026-07-01", "2026-08-01", "2026-09-01"], [1.0, 2.0, 3.0])
    assert [label for _, label in monthly.year_ticks()] == [
        "Jul 2026",
        "Aug 2026",
        "Sep 2026",
    ]
    # zero without clamping still pads both sides (building residual scatters)
    padded = charts.Frame(["2026-01-01", "2026-06-01"], [5.0, 20.0], zero=True)
    assert padded.ticks[0] < 0
    clamped = charts.Frame(
        ["2026-01-01", "2026-06-01"], [5.0, 20.0], zero=True, clamp_zero=True
    )
    assert clamped.ticks[0] == 0


def test_spearman_and_ranks():
    from apartments.site.research import _ranks, spearman

    assert _ranks([3.0, 1.0, 1.0, 2.0]) == [4.0, 1.5, 1.5, 3.0]
    assert spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)
    assert spearman([1, 2], [1, 2]) is None
    assert spearman([1, 1, 1], [1, 2, 3]) is None


def test_validation_page(client, research_file):
    data = json.loads(research_file.read_text())
    for e in data["entries"]:
        rows = e["splits"]["rows"]
        if e.get("psis"):
            rows["delta"] = e["psis"]["delta"] / 10
            rows["delta_se"] = 5.0
    served = next(e for e in data["entries"] if e["id"].startswith("m-test"))
    served["splits"]["units"] = {"run": "u", "delta": 120.0, "delta_se": 9.0}
    served["variance"]["descriptive"] = {"mean": 0.3, "median": 0.2}
    data["entries"].append(
        dict(served, id="m-test-gibbs", key="m-test-gibbs", sampler="gibbs")
    )
    research_file.write_text(json.dumps(data))
    html = client.get("/research/validation").get_data(as_text=True)
    assert "the rank correlation is <strong>1.00</strong>" in html
    assert "1 simple baseline far below" in html  # L0-mean left out
    assert "Same model, different implementations" in html
    assert ">gibbs</a>" in html and ">nuts</a>" in html
    assert "+120.0" not in html  # the unit split table is retired
    assert '<th scope="col" class="num">Descriptive</th>' in html
    assert "20.0%" in html  # descriptive as the median over draws
    assert "78.6%" in html  # the served fit is on the frontier with a breakdown
    empty = client.get("/research/validation?hardware=thelio+CPU").get_data(
        as_text=True
    )
    assert "No frontier fit on this hardware has a variance breakdown." in empty


def test_glossary_has_anchors_the_pages_link_to(client):
    html = client.get("/research/glossary").get_data(as_text=True)
    for anchor in (
        "psis-loo",
        "delta-elpd",
        "pareto-k",
        "elegance",
        "p-loo",
        "frontier",
        "servable",
    ):
        assert f'id="{anchor}"' in html
    assert "/research/glossary#psis-loo" in client.get("/research/validation").get_data(
        as_text=True
    )


def test_doc_links_and_markdown_rendering():
    from apartments.site.research import doc_link, render_markdown

    github = "https://github.com/gotnosocks/apartments/blob/master/"
    assert doc_link("dashboard.md") == github + "docs/dashboard.md"
    assert doc_link("model/a.md#b") == github + "docs/model/a.md#b"
    assert (
        doc_link("../config/main-analysis.json") == github + "config/main-analysis.json"
    )
    assert doc_link("#objective") == "#objective"
    assert doc_link("https://example.com/x") == "https://example.com/x"
    assert doc_link("../../outside.md") == "#"
    assert doc_link("/frontier/README.md") == github + "frontier/README.md"
    assert doc_link("ftp://example.com/x") == "ftp://example.com/x"
    assert doc_link("HTTP://example.com") == "HTTP://example.com"
    html, toc = render_markdown(
        "# Plan\n\nSee [the board](model/leaderboard/leaderboard.md).\n\n"
        "## Objective\n\n<script>alert(1)</script>\n\n## Objective\n\n| a | b |\n|---|---|\n| 1 | 2 |\n"
    )
    assert '<h2 id="plan">Plan</h2>' in html  # one level down
    assert '<h3 id="objective">' in html and '<h3 id="objective-2">' in html
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert github + "docs/model/leaderboard/leaderboard.md" in html
    assert "<table>" in html
    assert toc == [
        (2, "Plan", "plan"),
        (3, "Objective", "objective"),
        (3, "Objective", "objective-2"),
    ]


def test_plan_page_reads_the_current_plan(site_root, research_file, tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text("# Research plan\n\n## Goal\n\nFit fast.\n")
    app = create_app(site_root, research_data=research_file, research_plan=plan)
    client = app.test_client()
    html = client.get("/research/plan").get_data(as_text=True)
    assert '<a href="#goal">Goal</a>' in html and "Fit fast." in html
    plan.write_text("# Research plan\n\n## Goal\n\nFit faster.\n")
    import os

    os.utime(plan, ns=(1, 2_000_000_000_000_000_000))
    assert "Fit faster." in client.get("/research/plan").get_data(as_text=True)


def test_data_quality_page(client, research_file, data_quality):
    data = json.loads(research_file.read_text())
    data["data_quality"] = data_quality
    research_file.write_text(json.dumps(data))
    html = client.get("/research/data").get_data(as_text=True)
    assert "52,450" in html and "47,191" in html
    assert (
        '<code>quarantine-v2</code> <span class="tag">in the served model</span>'
        in html
    )
    assert "&lt;not&gt; open-market" in html  # rule text is escaped
    assert "Leaves out 188 listings in" in html and "Placed elsewhere" in html
    assert 'href="/quarantined"' in html


def test_research_navigation_stays_on_this_site(client):
    html = client.get("/research").get_data(as_text=True)
    for path in (
        "/research/board",
        "/research/history",
        "/research/validation",
        "/research/model",
        "/research/glossary",
        "/research/elegance",
        "/research/data",
        "/research/plan",
    ):
        assert f'href="{path}"' in html
    assert ":8500" not in html


def test_contents_titles_drop_markdown_and_images_resolve():
    from apartments.site.research import render_markdown

    html, toc = render_markdown("## The `walk` *scale*\n\n![map](img/map.png)\n")
    assert toc == [(3, "The walk scale", "the-walk-scale")]
    assert (
        "https://github.com/gotnosocks/apartments/raw/master/docs/img/map.png" in html
    )


def test_rent_map_page_and_data(client, site_root):
    page = client.get("/estimates/map").get_data(as_text=True)
    assert "no rent map for the served model yet" in page
    # the map script names the area from the build when the map does not
    assert 'data-area="Chelsea"' in page
    assert client.get("/estimates/map.json").status_code == 404
    current = (site_root / "current").resolve()
    (current / "map.json").write_text(
        json.dumps({"run": "m-test-run", "years": [2026]})
    )
    page = client.get("/estimates/map").get_data(as_text=True)
    assert 'data-src="/estimates/map.json"' in page and "rentmap.js" in page
    assert 'href="/estimates/map" aria-current="page"' in page
    data = client.get("/estimates/map.json")
    assert data.status_code == 200 and data.get_json()["run"] == "m-test-run"


def test_one_neighbourhood_shows_no_neighbourhood_controls(client):
    html = client.get("/listings").get_data(as_text=True)
    assert 'name="nb"' not in html
    assert 'name="nb"' not in client.get("/buildings").get_data(as_text=True)


def test_neighbourhoods_filter_listings_and_buildings(
    tmp_path, make_bundle, research_file
):
    from apartments.site import build

    bundle = make_bundle(
        tmp_path / "nb",
        neighbourhoods={"134-west-23-street-new_york": "West Village"},
    )
    root = tmp_path / "nb-site"
    build.build(bundle, root, scope="Chelsea and West Village")
    client = create_app(root, research_data=research_file).test_client()
    html = client.get("/listings").get_data(as_text=True)
    assert '<option value="West Village">West Village (2)</option>' in html
    assert "(West Village)" in html  # next to the building in the table
    wv = client.get("/listings?nb=West+Village").get_data(as_text=True)
    assert wv.count('href="/listings/a') == 2 and "/listings/a1" not in wv
    assert (
        client.get("/listings?nb=Nowhere")
        .get_data(as_text=True)
        .count('href="/listings/a')
        == 6
    )  # an unknown neighbourhood is ignored
    buildings = client.get("/buildings?nb=Chelsea").get_data(as_text=True)
    assert "The Grove" in buildings and "134 West 23rd Street" not in buildings
    page = client.get("/buildings/134-west-23-street-new_york").get_data(as_text=True)
    assert '<p class="subline">West Village · ' in page
    # several neighbourhoods are named by their count, not listed (Ben, 2026-10-09)
    estimates = client.get("/estimates").get_data(as_text=True)
    assert "<h1>All rental listings, with" in estimates
    assert "in an average building across both neighbourhoods," in estimates
    assert "Chelsea and West Village" not in estimates
    rent_map = client.get("/estimates/map").get_data(as_text=True)
    assert 'data-area="both neighbourhoods"' in rent_map
    assert "in each building across both neighbourhoods," in rent_map
    home = client.get("/").get_data(as_text=True)
    assert "Every scraped rental listing in both neighbourhoods," in home
    about = client.get("/about").get_data(as_text=True)
    assert "listings in both neighbourhoods (Chelsea and West Village)," in about
    story = client.get("/research/story").get_data(as_text=True)
    assert "one one-bedroom across both neighbourhoods ask" in story


def test_elegance_page_lists_every_judgement(client):
    html = client.get("/research/elegance").get_data(as_text=True)
    # the modeling session's definition, word for word
    assert "how coherent a model is as a statistical model of how asks arise" in html
    assert "Ties in accuracy go to the more elegant model." in html
    assert "renter" not in html
    # newest first; each design links to a fit on the board, with its p_loo
    listing = html[html.index("<h2>Every judgement</h2>") :]  # after the standings
    assert listing.index("m-other/unitdesc-v1") < listing.index("m-cpu/unitdesc-v1")
    assert "<code>m-other/unitdesc-v1</code></a>" in html
    assert "(413 effective parameters)" in html
    assert "<code>m-test/unitdesc-v1</code> is more elegant" in html
    assert "both judges agreed" in html
    assert "about equally elegant" in html
    assert "the judges disagreed, so the pair counts as equal" in html
    assert "<i>term</i>" not in html and "&lt;i&gt;term" in html  # escaped
    assert 'aria-current="page">Elegance' in html
    assert client.get("/research/simplicity").status_code == 404


def test_fit_page_shows_its_elegance_judgements(client, research_file):
    html = client.get("/research/fits/m-other").get_data(as_text=True)
    assert 'id="elegance"' in html
    served = '<a href="/research/fits/m-test/unitdesc-v1/nuts@aaaaaaa">'
    assert served + "<code>m-test/unitdesc-v1</code></a>" in html
    assert "less elegant" in html and "renter" not in html
    mine = client.get("/research/fits/m-test/unitdesc-v1/nuts@aaaaaaa")
    assert "Effective parameters</span>" in mine.get_data(as_text=True)
    assert "Complexity" not in html
    lone = client.get("/research/fits/L0-mean").get_data(as_text=True)
    assert "No judge has compared this design with another yet." in lone
    frontier = client.get("/research").get_data(as_text=True)
    assert "Complexity" not in frontier and "2 pairs" in frontier
    assert "less elegant than 1" in frontier  # the frontier table
    assert "renter" not in frontier


def _with_exploration(research_file):
    """The research data with two exploration fits of the served design (one
    on a subset) and the exploration header."""
    data = json.loads(research_file.read_text())
    served = next(e for e in data["entries"] if e["id"].startswith("m-test/"))
    quick = dict(
        served,
        id="m-test/unitdesc-v1/nuts@bbbbbbb [quick]",
        key="m-test/unitdesc-v1/nuts@bbbbbbb [quick]",
        tier={"name": "exploration", "draws": 200, "warmup": 200, "chains": 2},
        passes_checks=False,
        frontier=True,
        current_best=False,
        fit_seconds=120.0,
        psis={"delta": 5100.0, "delta_se": 130.0},
        why_not_served="it is an exploration fit",
        available_at="2026-09-29T09:00:00+00:00",
        splits={"rows": {"run": "m-test-quick-run"}},
        elegance=[],
    )
    subset = dict(
        quick,
        id="m-test/unitdesc-v1/nuts@ccccccc [sub]",
        key="m-test/unitdesc-v1/nuts@ccccccc [sub]",
        tier={"name": "exploration", "draws": 200, "subset": "tune-b35-v1"},
        psis=None,
        frontier=False,
        splits={"rows": {"run": "m-test-sub-run"}},
    )
    served["tier"] = {"name": "full", "draws": 1000, "warmup": 1000, "chains": 4}
    data["entries"] += [quick, subset]
    data["snapshots"][-1]["by_class"]["thelio RTX 2060 SUPER"]["frontier"].append(
        quick["key"]
    )
    data["exploration"] = {
        "as_of": "2026-10-01T09:30:00+00:00",
        "goal": "Find <b>fast</b> designs on Chelsea and West Village.",
        "dataset": "chelsea-wv-v1",
        "tiers": [
            {
                "name": "exploration",
                "draws": 200,
                "warmup": 200,
                "chains": 2,
                "subset": None,
                "description": "Ranks designs in minutes.",
            },
            {
                "name": "full",
                "draws": 1000,
                "warmup": 1000,
                "chains": 4,
                "subset": None,
                "description": "Passes the gate; can be served.",
            },
        ],
        "notes": ["200 draws rank designs like 1,000 do."],
    }
    research_file.write_text(json.dumps(data))
    return quick, subset


def test_exploration_fits_count_on_the_frontier(client, research_file):
    quick, subset = _with_exploration(research_file)
    html = client.get("/research").get_data(as_text=True)
    # a diamond on the exploration fits' own chart, none on the full fits'
    full = html[html.index('id="full-fits"') : html.index('id="exploration-fits"')]
    explore = html[html.index('id="exploration-fits"') :]
    explore = explore[: explore.index("</section>")]
    assert '<path class="fit' not in full and "<circle" in full
    assert (
        '<path class="fit frontier' in explore and '<circle class="fit' not in explore
    )
    assert "2-hour limit" not in explore
    # the tooltip names the kind, then the tier (JSON escapes the dot)
    assert "On the frontier \\u00b7 exploration fit" in html
    # in the frontier table, tagged, and not marked as failing the checks
    table = html[html.index("<h2>On the frontier") :]
    assert quick["key"] in table and 'class="tag exploration"' in table
    # the header: goal escaped, tiers and notes
    assert "Find &lt;b&gt;fast&lt;/b&gt; designs" in html
    assert "Ranks designs in minutes." in html and "<code>chelsea-wv-v1</code>" in html
    assert "200 draws rank designs like 1,000 do." in html
    assert 'Exploration fits</span><span class="tile-value">1<' in html
    # the subset fit is hidden unless asked for
    assert subset["key"] not in html
    shown = client.get("/research?subsets=1").get_data(as_text=True)
    assert subset["key"] in shown
    # a legend that only describes its tiers, as the live data does
    data = json.loads(research_file.read_text())
    data["exploration"]["tiers"] = [
        {"name": "exploration", "description": "Short."},
        {"name": "full", "description": "Full."},
    ]
    research_file.write_text(json.dumps(data))
    described = client.get("/research").get_data(as_text=True)
    card = described[
        described.index("The current exploration") : described.index(
            "Full fits: accuracy against fit time"
        )
    ]
    assert "<td>Short.</td>" in card and ">Draws<" not in card
    # no exploration header: no card, the fits still drawn
    research_file.write_text(json.dumps(dict(data, exploration=None)))
    plain = client.get("/research").get_data(as_text=True)
    assert (
        "The current exploration" not in plain and '<path class="fit frontier' in plain
    )


def test_frontier_charts_zoom_by_url(client, research_file):
    _with_exploration(research_file)
    html = client.get("/research").get_data(as_text=True)
    assert '"zoom":"f"' in html and '"zoom":"e"' in html
    assert "Drag across the chart to zoom in" in html and "Reset zoom" not in html
    assert "Zoom to the frontier" in html and "?fx0=" in html
    # nothing inside the box: said so, with the count and a way back
    empty = client.get("/research?fy0=1e8&fy1=2e8").get_data(as_text=True)
    assert "No fit falls inside the zoomed range." in empty
    assert "Zoomed in: 0 of" in empty and 'href="?#full-fits">Reset zoom' in empty
    # one chart's zoom keeps the other's, and the hand-set form keeps both
    both = client.get("/research?ex0=0&ex1=50&fx0=0&fx1=1e6").get_data(as_text=True)
    assert 'href="?ex0=0&amp;ex1=50#full-fits">Reset zoom' in both
    assert '<input type="hidden" name="ex0" value="0">' in both
    assert 'name="fx1" value="1e+06"' in both
    # an unscored fit is counted under its own tier's chart
    subsets = client.get("/research?subsets=1").get_data(as_text=True)
    assert "1 has no PSIS-LOO score at all" in subsets
    # a range that is empty, reversed or not a number is ignored
    for bad in (
        "fx0=abc&fx1=5",
        "fy0=5&fy1=1",
        "fx0=1&fx1=1",
        "fx0=nan&fx1=inf",
        "fx0=-1e308&fx1=1e308",
        "fx0=37.123456789&fx1=37.12345678900001",
    ):
        page = client.get(f"/research?{bad}").get_data(as_text=True)
        full = page[page.index('id="full-fits"') : page.index('id="exploration-fits"')]
        assert "Reset zoom" not in full, bad


def test_board_filters_by_tier(client, research_file):
    quick, _ = _with_exploration(research_file)
    both = client.get("/research/board").get_data(as_text=True)
    assert quick["key"] in both and 'name="tier"' in both
    only = client.get("/research/board?tier=exploration").get_data(as_text=True)
    assert quick["key"] in only and "<code>m-other</code>" not in only
    assert 'href="/research/fits/m-test/unitdesc-v1/nuts@aaaaaaa"' not in only
    full = client.get("/research/board?tier=full").get_data(as_text=True)
    assert quick["key"] not in full and "<code>m-other</code>" in full
    ignored = client.get("/research/board?tier=bogus").get_data(as_text=True)
    assert quick["key"] in ignored


def test_exploration_fit_page_links_its_full_fits(client, research_file):
    quick, _ = _with_exploration(research_file)
    from urllib.parse import quote

    html = client.get(f"/research/fits/{quote(quick['key'])}").get_data(as_text=True)
    assert "<h2>An exploration fit</h2>" in html
    assert "No: it is an exploration fit." in html
    assert "200 over 2 chains" in html
    served = 'href="/research/fits/m-test/unitdesc-v1/nuts@aaaaaaa"'
    assert served in html[html.index("Full fits of the same design") :]
    full = client.get("/research/fits/m-test/unitdesc-v1/nuts@aaaaaaa").get_data(
        as_text=True
    )
    assert "An exploration fit" not in full
    assert 'id="exploration-fit"' in client.get("/research/glossary").get_data(
        as_text=True
    )


def test_tiers_without_research_fields():
    from apartments.site import research

    assert research.data_rules_of(
        {"id": "m7/f-v5/gibbs@a8ef50d+unit-labels-v1+quarantine-v2 [x]"}
    ) == ("quarantine-v2", "unit-labels-v1")
    assert research.data_rules_of({"id": "m0/base-v1/nuts@5cc0809"}) == ()
    quick = {
        "id": "m/f/g@b+q2",
        "design": "m",
        "feature_set": "f",
        "tier": {"name": "exploration"},
    }
    same = {"id": "m/f/g@c+q2", "design": "m", "feature_set": "f", "key": "same"}
    other = {"id": "m/f/g@d+q1", "design": "m", "feature_set": "f", "key": "q1"}
    found = research.full_fits_of({"entries": [quick, same, other]}, quick)
    assert [e["key"] for e in found] == ["same"]

    assert research.tier_of({}) == "full"
    assert research.tier_of({"tier": {"name": "nonsense"}}) == "full"
    explore = {"tier": {"name": "exploration"}, "passes_checks": True}
    assert research.serve_status(explore) == (
        "no",
        "an exploration fit, for tracking the research only",
    )
    assert research.subset_fit({"tier": {"name": "exploration", "subset": "tune-x"}})


def test_one_design_measured_twice_is_joined(client, research_file):
    from apartments.site import research

    _with_exploration(research_file)
    html = client.get("/research").get_data(as_text=True)
    # two designs measured twice: m-test (the 200-draw exploration fit and
    # the 1,000-draw full fit) and m-other (m-other and m-failing). Only
    # m-other's fits share a chart: m-test's are one on each, unjoined, and
    # its exploration diamond is not faded where nothing explains it.
    assert html.count('<polyline class="measured"') == 1
    assert 'class="fit frontier faded"' not in html
    assert "One design at several draw counts" in html
    assert '<td class="num">1,000</td>' in html  # the Draws column

    def fit(key, draws, at, delta=1.0, rules=""):
        entry = {
            "id": f"m/f/g@{key}{rules}",
            "design": "m",
            "feature_set": "f",
            "available_at": at,
        }
        return {"entry": entry, "delta": delta, "draws": draws}

    a, b, c = fit("a", 300, "1"), fit("b", 1500, "2"), fit("c", 1500, "3")
    other_rules = fit("d", 600, "4", rules="+q1")
    unscored = fit("e", 9000, "5", delta=None)
    research.group_measurements([a, b, c, other_rules, unscored])
    assert a["group"] == b["group"] == c["group"] == 0
    assert (a["faded"], b["faded"], c["faded"]) == (True, True, False)  # newest
    assert other_rules["group"] is None and not other_rules["faded"]
    assert unscored["group"] is None


def test_time_limit_line_drawn_only_when_fits_reach_it():
    from apartments.site import charts

    def chart(minutes):
        point = {"x": minutes, "y": 1.0, "kind": "other", "title": "f", "rows": []}
        return str(
            charts.fit_scatter(
                [point],
                label="t",
                x_title="x",
                y_title="y",
                x_format=str,
                y_format=str,
                x_line=(120, "2-hour limit for a full fit"),
            )
        )

    assert "2-hour limit" not in chart(10)
    assert "2-hour limit" in chart(150)


def test_fit_page_draws_the_design(client):
    from urllib.parse import quote

    served = client.get("/research/fits/" + quote("m-test/unitdesc-v1/nuts@aaaaaaa"))
    html = served.get_data(as_text=True)
    assert 'id="structure"' in html and "<math" in html
    assert "2,296" not in html and "10 buildings" in html  # the fixture's sizes
    assert "Building drift over time" in html and "This is the served design" in html
    other = client.get("/research/fits/m-other").get_data(as_text=True)
    assert "Drops building drift over time" in other
    assert "part-chip off" in other  # parts it leaves out are drawn dashed


def test_designs_page(client):
    html = client.get("/research/designs").get_data(as_text=True)
    assert "Which parts each design has" in html
    assert '<span class="feature-sets">unitdesc-v1</span>' in html
    assert html.index("<code>m-test</code>") < html.index("<code>m-other</code>")
    assert "Drops building drift over time" in html
    assert "; Drops" not in html


def test_pages_without_recorded_structure(tmp_path, site_root):
    from apartments.site.web import create_app

    from .conftest import research_data

    data = research_data()
    for e in data["entries"]:
        e.pop("model", None)
        e.pop("sizes", None)
    path = tmp_path / "data.json"
    path.write_text(json.dumps(data))
    client = create_app(
        site_root, allowed_hosts=["thelio.example.ts.net"], research_data=path
    ).test_client()
    fit = client.get("/research/fits/m-other").get_data(as_text=True)
    assert "holds no structure for this design" in fit
    designs = client.get("/research/designs").get_data(as_text=True)
    assert "No design on the board records its structure yet" in designs
    # The served model's page falls back to the bundle's own ModelConfig.
    served = client.get("/research/model").get_data(as_text=True)
    assert 'id="structure"' in served and "Building drift over time" in served


def test_designs_page_without_the_served_design(tmp_path, site_root):
    from apartments.site.web import create_app

    from .conftest import research_data

    data = research_data()
    data["entries"] = [e for e in data["entries"] if e["design"] != "m-test"]
    path = tmp_path / "data.json"
    path.write_text(json.dumps(data))
    client = create_app(
        site_root, allowed_hosts=["thelio.example.ts.net"], research_data=path
    ).test_client()
    html = client.get("/research/designs").get_data(as_text=True)
    assert "<code>m-other</code>" in html
    assert "not on the board, so no design is compared" in html
    assert "The same structure." not in html


def test_part_chips_leave_the_listing_chips_alone():
    css = (
        Path(__file__).parents[2] / "src/apartments/site/static/site.css"
    ).read_text()
    anatomy_css = css[css.index("/* A design's structure") :]
    assert "\n.chip" not in anatomy_css and ".chips" not in anatomy_css


def test_fit_time_says_how_busy_the_fits_cores_were(client):
    from urllib.parse import quote

    html = client.get(
        "/research/fits/" + quote("m-test/unitdesc-v1/nuts@aaaaaaa")
    ).get_data(as_text=True)
    assert "0.2 other cores busy on the fit's cores" in html
    assert "clean timing" in html and "#fit-cores" in html
    glossary = client.get("/research/glossary").get_data(as_text=True)
    assert 'id="fit-cores"' in glossary


def test_designs_page_caps_the_feature_sets_shown():
    from apartments.site.research import designs

    from .conftest import research_data

    data = research_data()
    base = next(e for e in data["entries"] if e["design"] == "m-other")
    data["entries"] += [
        dict(base, feature_set=f"fs-{i}", key=f"m-other-{i}") for i in range(5)
    ]
    rows, _ = designs(data, "m-test-run")
    other = next(r for r in rows if r["name"] == "m-other")
    assert len(other["feature_sets"]) == 6


def test_a_build_from_before_neighbourhoods_still_serves(client, site_root):
    # Builds before neighbourhoods have no neighbourhood columns or stats (an
    # older build can still be current when new code deploys).
    db = sqlite3.connect(site_root / "current" / "site.sqlite")
    db.execute("DROP INDEX listings_neighbourhood")
    for table in ("listings", "buildings"):
        db.execute(f"ALTER TABLE {table} DROP COLUMN neighbourhood")
    stats = json.loads(
        db.execute("SELECT value FROM meta WHERE key = 'stats'").fetchone()[0]
    )
    stats.pop("neighbourhoods", None)
    db.execute("UPDATE meta SET value = ? WHERE key = 'stats'", (json.dumps(stats),))
    db.commit()
    db.close()
    for path in (
        "/",
        "/estimates",
        "/listings",
        "/listings?nb=Chelsea",
        "/listings?status=current",
        "/buildings",
        f"/buildings/{GROVE}",
        "/units/u1",
        "/listings/a1",
        "/estimates/map",
    ):
        assert client.get(path).status_code == 200, path
    response = client.get("/listings.csv")
    rows = list(csv.DictReader(io.StringIO(response.get_data(as_text=True))))
    assert rows and "neighbourhood" not in rows[0]


def test_price_labels_are_explained_where_they_appear(client):
    listings = client.get("/listings").get_data(as_text=True)
    assert "Typical rent, 95% range" in listings
    assert "the same % gap can be typical for one apartment" in listings
    page = client.get("/listings/a2").get_data(as_text=True)
    assert "of the asks the model expects for this apartment" in page
    assert "lower than 90% of comparable asks" not in page
    assert "“not stated”" in page


def test_research_model_page_shows_a_pending_switch(site_root, research_file):
    data = json.loads(research_file.read_text())
    data["autoselect"] = {
        "action": "switch",
        "run": "m-new-run",
        "reason": "The incumbent cannot be served.",
        "checked": [{"run": "m-new-run", "psis": 12.0, "psis_pm": 4.0}],
    }
    served = next(e for e in data["entries"] if e["id"].startswith("m-test/"))
    served["frontier"] = False
    served["current_best"] = False
    research_file.write_text(json.dumps(data))
    html = (
        create_app(site_root, research_data=research_file)
        .test_client()
        .get("/research/model")
        .get_data(as_text=True)
    )
    assert "A switch is pending." in html and "<code>m-new-run</code>" in html
    assert (
        "The incumbent cannot be served." in html
    )  # a pending switch's incumbent is this one
    assert "<td>chosen; not published yet</td>" in html
    assert "On the frontier</dt><dd>no" in html
    assert "another fit is at least as accurate" in html


def test_research_model_page_explains_a_keep_on_old_rules(site_root, research_file):
    data = json.loads(research_file.read_text())
    data["autoselect"] = {
        "action": "keep",
        "incumbent_eligible": False,
        "eligible": [],
        "checked": [],
        "reason": "no eligible fit; the incumbent stays although it was fit with quarantine-v6.",
    }
    research_file.write_text(json.dumps(data))
    app = create_app(site_root, research_data=research_file)
    html = app.test_client().get("/research/model").get_data(as_text=True)
    assert "Waiting for a refit on the current data rules." in html
    assert "no fit on the new rules has landed yet" in html
    assert "this model stays although it was fit with quarantine-v6." in html
    data["autoselect"]["eligible"] = [{"run": "m-new-run"}]
    research_file.write_text(json.dumps(data))
    app = create_app(site_root, research_data=research_file)
    html = app.test_client().get("/research/model").get_data(as_text=True)
    assert "Waiting for a refit on the current data rules." in html
    assert "no fit on the new rules has landed yet" not in html
    data["autoselect"]["eligible"] = []
    data["autoselect"]["incumbent_eligible"] = True
    research_file.write_text(json.dumps(data))
    app = create_app(site_root, research_data=research_file)
    html = app.test_client().get("/research/model").get_data(as_text=True)
    assert "Waiting for a refit" not in html


def test_fits_on_earlier_data_are_drawn_apart(client, research_file):
    _with_exploration(research_file)
    data = json.loads(research_file.read_text())
    quick = next(e for e in data["entries"] if e["key"].endswith("[quick]"))
    old = dict(
        quick,
        id="m-test/unitdesc-v1/nuts@ddddddd [old]",
        key="m-test/unitdesc-v1/nuts@ddddddd [old]",
        psis=None,
        frontier=False,
        psis_prior={
            "delta": 777.0,
            "se": 12.0,
            "mcse": 1.0,
            "baseline": "base-old",
            "dataset": "chelsea-wv-old",
        },
        splits={"rows": {"run": "m-test-old-run"}},
    )
    data["entries"].append(old)
    research_file.write_text(json.dumps(data))
    html = client.get("/research").get_data(as_text=True)
    card = html[html.index('id="exploration-fits"') :]
    card = card[: card.index("</section>")]
    # the count comes before the chart, and the earlier fit is in its own chart
    notice = card.index('class="notice"')
    assert notice < card.index("<svg")
    assert "1 more</strong> was trained on the earlier data" in card
    assert card.index('id="e-earlier"') < card.index("+777.0")
    main = card[: card.index('id="e-earlier"')]
    assert "ddddddd" not in main
    full = html[html.index('id="full-fits"') : html.index('id="exploration-fits"')]
    assert "earlier data" not in full


def test_earlier_data_chart_is_zoomable_and_joins_its_best(client, research_file):
    _with_exploration(research_file)
    data = json.loads(research_file.read_text())
    quick = next(e for e in data["entries"] if e["key"].endswith("[quick]"))
    for tag, seconds, delta in (
        ("a", 300.0, 500.0),
        ("b", 600.0, 900.0),
        ("c", 900.0, 400.0),
    ):
        key = f"m-test/unitdesc-v1/nuts@ddddddd [old-{tag}]"
        data["entries"].append(
            dict(
                quick,
                id=key,
                key=key,
                fit_seconds=seconds,
                psis=None,
                frontier=False,
                psis_prior={
                    "delta": delta,
                    "se": 12.0,
                    "mcse": 1.0,
                    "baseline": "base-old",
                    "dataset": "chelsea-wv-old",
                },
                splits={"rows": {"run": f"m-test-old-{tag}"}},
            )
        )
    research_file.write_text(json.dumps(data))
    html = client.get("/research").get_data(as_text=True)
    card = html[html.index('id="e-earlier"') :]
    card = card[: card.index("</section>")]
    # drawn by Chart.js, zoomed with its own URL prefix
    spec = json.loads(card.split('class="chart-spec">')[1].split("</script>")[0])
    assert spec["zoom"] == "ep" and spec["line"] == "dashed"
    on_line = {p["y"] for p in spec["points"] if p["on_line"]}
    assert on_line == {500.0, 900.0}
    assert "The best fits on the earlier data, joined" in card
    assert "&lt;span" not in card


def test_best_so_far_skips_dominated_and_ineligible_points():
    from apartments.site.web import best_so_far

    points = [
        {"x": 1, "y": 1, "kind": "other"},
        {"x": 2, "y": 3, "kind": "failing"},
        {"x": 3, "y": 2, "kind": "other"},
        {"x": 4, "y": 4, "kind": "other"},
    ]
    assert best_so_far(points, lambda p: True) == {0, 1, 3}
    assert best_so_far(points, lambda p: p["kind"] != "failing") == {0, 2, 3}


def test_frontier_charts_join_their_line(client, research_file):
    _with_exploration(research_file)
    data = json.loads(research_file.read_text())
    quick = next(e for e in data["entries"] if e["key"].endswith("[quick]"))
    slower = dict(
        quick,
        id="m-test/unitdesc-v1/nuts@eeeeeee [slow]",
        key="m-test/unitdesc-v1/nuts@eeeeeee [slow]",
        fit_seconds=900.0,
        psis={"delta": 5300.0, "delta_se": 100.0},
        splits={"rows": {"run": "m-test-slow-run"}},
    )
    data["entries"].append(slower)
    snap = data["snapshots"][-1]["by_class"]["thelio RTX 2060 SUPER"]
    snap["frontier_by_tier"] = {
        "exploration": [quick["key"], slower["key"]],
        "full": snap["frontier"],
    }
    research_file.write_text(json.dumps(data))
    html = client.get("/research").get_data(as_text=True)
    card = html[html.index('id="exploration-fits"') :]
    card = card[: card.index("</section>")]
    # both failing exploration fits are on the dashed line, said so
    assert card.count('class="frontier-line dashed"') == 1
    assert "includes fits that fail the convergence" in card


def test_values_that_round_to_zero_carry_no_sign():
    assert charts.pct(-0.3) == "0%"
    assert charts.pct(-0.04, digits=1) == "0.0%"
    assert charts.pct(-0.6) == "−1%"
    assert charts.usd(-0.4, signed=True) == "$0"
    assert charts.usd(-27, signed=True) == "−$27"


def test_about_shows_calibration_by_year_and_names_narrow_years(client, site_root):
    path = (site_root / "current" / "site.sqlite").resolve()
    db = sqlite3.connect(path)
    stats = json.loads(
        db.execute("SELECT value FROM meta WHERE key='stats'").fetchone()[0]
    )
    stats["calibration_by_year"] = [
        {
            "year": 2010,
            "n": 307,
            "cover95": 0.88,
            "cover80": 0.67,
            "mean_log_residual": 0.01,
        },
        {
            "year": 2015,
            "n": 900,
            "cover95": 0.95,
            "cover80": 0.80,
            "mean_log_residual": -0.004,
        },
    ]
    db.execute("UPDATE meta SET value=? WHERE key='stats'", (json.dumps(stats),))
    db.commit()
    db.close()
    html = client.get("/about").get_data(as_text=True)
    assert 'id="calibration-by-year"' in html
    assert "in some years (2010) than in others" in html
    assert '<td class="num">67%</td>' in html and "−0.4%" in html


def test_research_pages_open_on_the_served_fits_hardware():
    from apartments.site import research

    def entry(hw, run):
        return {"hardware_class": hw, "splits": {"rows": {"run": run}}}

    data = {
        "entries": [
            entry(research.TARGET_HARDWARE, "m-old"),
            entry(research.TARGET_HARDWARE, "m-older"),
            entry("modal A100", "m-served"),
        ]
    }
    assert research.default_hardware(data, "m-served") == "modal A100"
    assert research.default_hardware(data, "m-gone") == research.TARGET_HARDWARE
    assert research.default_hardware(data, "") == research.TARGET_HARDWARE


def test_site_is_titled_nyc_rents(client):
    html = client.get("/").get_data(as_text=True)
    assert "· NYC Rents</title>" in html
    assert 'class="brand" href="/">NYC Rents</a>' in html
    assert "<h1>NYC Rents: estimates and research</h1>" in html
    story = client.get("/research/story").get_data(as_text=True)
    assert "· NYC Rents</title>" in story

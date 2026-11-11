"""The Estimates section: drift-building's held-out estimates, as published by
`rentfrontier.drift_estimates publish` into the site's `estimates/` folder."""

import csv
import io
import json
import re

import pytest

from apartments.site import estimates
from apartments.site.web import create_app


def _rows(page: str) -> list[str]:
    """The listing ids the list page links to, in order."""
    return re.findall(r'href="/listings/(\d+)"', page)


def test_overview_names_the_model_runs_gates_and_accuracy(client):
    page = client.get("/estimates").get_data(as_text=True)
    assert "drift-building" in page
    assert "drift-latest-run" in page and "drift-market-run" in page
    assert "passed the convergence test" in page
    # exp(0.0953) - 1 is a 10.0% miss on a typical ad.
    assert "10.0%" in page
    assert "81.0%" in page and "94.7%" in page
    assert 'href="/">Deals</a>' in page and 'href="/listings.csv"' in page
    assert "Market reference rent" not in page


def test_the_list_is_newest_first_and_says_where_each_ask_sits(client):
    page = client.get("/listings").get_data(as_text=True)
    assert _rows(page) == ["1004", "1005", "1002", "1001", "1003"]
    assert "<strong>5</strong> estimates" in page
    assert "250 West 19th Street" in page and "West Village" in page
    assert "https://streeteasy.com/rental/1001" in page
    # below_share 0.05: the ask is lower than 95% of the asks the model expects.
    assert "95.0%" in page
    assert "$2,440 to $3,660" in page  # the 80% range of listing 1001


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("status=current", ["1004", "1005"]),
        ("status=past", ["1002", "1001", "1003"]),
        ("beds=0&beds=2", ["1002", "1003"]),
        ("beds=4", []),
        ("min_ask=3000&max_ask=6000", ["1004", "1002"]),
        ("from=2020&to=2024", ["1002", "1001"]),
        ("nb=West+Village", ["1005"]),
        ("nb=west-village", ["1005"]),
        ("nb=Nowhere", ["1004", "1005", "1002", "1001", "1003"]),
        ("q=134+west", ["1003"]),
        ("q=bank", ["1005"]),
        ("sort=low", ["1001", "1003", "1004", "1005", "1002"]),
        ("sort=high", ["1002", "1005", "1004", "1003", "1001"]),
        ("sort=ask", ["1003", "1001", "1004", "1002", "1005"]),
        ("sort=ask_desc", ["1005", "1002", "1004", "1001", "1003"]),
        # The earlier listings page's links keep working.
        ("status=current&sort=diff_pct", ["1004", "1005"]),
        ("sort=diff_pct&order=desc", ["1002", "1005", "1004", "1003", "1001"]),
        ("sort=nonsense&beds=9&min_ask=abc", ["1004", "1005", "1002", "1001", "1003"]),
    ],
)
def test_the_list_filters_and_sorts(client, query, expected):
    response = client.get(f"/listings?{query}")
    assert response.status_code == 200
    assert _rows(response.get_data(as_text=True)) == expected


def test_a_filtered_list_sums_up_its_rows(client):
    page = client.get("/listings?status=past").get_data(as_text=True)
    assert "<strong>3</strong> estimates match" in page
    assert "median ask <strong>$2,600</strong>" in page
    # Listing 1002's ask is above its 80% range and inside its 95% range.
    assert "67% asked within the model's 80% range" in page
    assert "100% within its 95% range" in page


def test_the_list_pages_by_fifty(tmp_path, write_estimates, estimate_row):
    root = tmp_path / "site"
    rows = [
        estimate_row(
            str(2000 + i),
            f"x{i}",
            "latest",
            "b",
            f"{i} Main Street",
            "chelsea",
            1.0,
            f"2025-01-{1 + i % 28:02d}",
            3000.0 + i,
            3000.0,
            0.5,
            0,
        )
        for i in range(120)
    ]
    write_estimates(root, rows)
    client = create_app(root).test_client()
    first = client.get("/listings?sort=ask").get_data(as_text=True)
    assert _rows(first) == [str(2000 + i) for i in range(50)]
    assert "Page 1 of 3" in first and 'href="/listings?sort=ask&amp;page=2"' in first
    last = client.get("/listings?sort=ask&page=3").get_data(as_text=True)
    assert _rows(last) == [str(2000 + i) for i in range(100, 120)]
    # A page past the last shows the last.
    assert _rows(client.get("/listings?sort=ask&page=99").get_data(as_text=True)) == (
        _rows(last)
    )
    body = client.get("/listings.csv?sort=ask").get_data(as_text=True)
    assert len(list(csv.reader(io.StringIO(body)))) == 121


def test_the_csv_has_every_column_and_the_same_filters(client):
    response = client.get("/listings.csv?status=past&sort=low")
    assert response.status_code == 200 and response.mimetype == "text/csv"
    table = list(csv.reader(io.StringIO(response.get_data(as_text=True))))
    assert tuple(table[0]) == estimates.COLUMNS
    assert [r[0] for r in table[1:]] == ["1001", "1003", "1002"]
    row = dict(zip(table[0], table[1], strict=True))
    assert row["audit_id"] == "a2" and row["source"] == "latest"
    assert float(row["model_lo80"]) == 2440.0


def test_the_detail_page_by_listing_id_and_by_audit_id(client):
    page = client.get("/listings/1002").get_data(as_text=True)
    assert client.get("/listings/a4").get_data(as_text=True) == page
    assert "250 West 19th Street" in page and "2 BR" in page
    assert "$5,200" in page and "$4,000" in page
    assert "$3,600" in page and "$4,400" in page  # the 50% range
    assert "$2,800" in page and "$5,200" in page  # the 95% range
    assert 'class="istrip"' in page
    assert "This ask is <strong>high</strong>" in page
    assert "earlier ads the" in page and "<strong>none</strong>" in page
    assert "new apartment" in page
    assert "drift-latest-run" in page
    assert "https://streeteasy.com/rental/1002" in page


def test_the_detail_page_of_an_ad_on_the_market(client):
    page = client.get("/listings/1004").get_data(as_text=True)
    assert "drift-market-run" in page and "Nov 9, 2026" in page
    assert "<strong>2</strong>" in page and "narrower" in page
    assert "within the usual range" in page


@pytest.mark.parametrize("key", ["a1", "q1"])
def test_an_ad_without_a_held_out_estimate_is_a_plain_404(client, key):
    # The sqlite build of the fixture holds both ads: `a1` is an apartment's earlier
    # ad and `q1` is a quarantined one. The estimates table holds neither.
    response = client.get(f"/listings/{key}")
    assert response.status_code == 404
    page = response.get_data(as_text=True)
    assert "only for the ads it held out" in page
    assert "/buildings/" not in page and "retail" not in page.lower()


def test_an_unknown_ad_is_a_plain_404(client):
    response = client.get("/listings/no-such-ad")
    assert response.status_code == 404
    page = response.get_data(as_text=True)
    assert "only for the ads it held out" in page
    assert "the newest ad of each apartment, and the ads on the market" in page


@pytest.mark.parametrize("path", ["/estimates", "/listings", "/listings/1001"])
def test_no_folder_is_a_503(tmp_path, path):
    client = create_app(tmp_path / "site").test_client()
    response = client.get(path)
    assert response.status_code == 503
    assert "No estimates have been published yet." in response.get_data(as_text=True)
    assert client.get("/listings.csv").status_code == 503


def test_a_table_that_is_not_its_metas_is_refused(tmp_path, write_estimates):
    root = tmp_path / "site"
    folder = write_estimates(root, estimates_sha256="0" * 64)
    client = create_app(root).test_client()
    for path in ("/estimates", "/listings", "/listings.csv", "/listings/1001"):
        response = client.get(path)
        assert response.status_code == 503
        assert "do not match" in response.get_data(as_text=True)
    # The next publish, with its own sha256, is served.
    write_estimates(root)
    assert (
        json.loads((folder / "meta.json").read_text())["estimates_sha256"] != "0" * 64
    )
    assert client.get("/listings").status_code == 200


def test_load_reads_a_new_publish(tmp_path, write_estimates, estimate_row):
    root = tmp_path / "site"
    assert estimates.load(root) is None
    write_estimates(root)
    first = estimates.load(root)
    assert first.meta["ads"]["all"] == 5 and estimates.load(root) is first
    write_estimates(
        root,
        [
            estimate_row(
                "9", "z", "market", "b", "", "", 1.0, "2026-11-09", 1.0, 1.0, 0.5, 0
            )
        ],
    )
    second = estimates.load(root)
    assert second is not first
    assert second.count(estimates.Choice()) == 1


def test_areas_by_value_name_and_borough():
    hoods = {"chelsea": 3, "west-village": 1, "Williamsburg": 2}
    assert estimates.areas("Chelsea", hoods) == ["chelsea"]
    assert estimates.areas("west-village", hoods) == ["west-village"]
    assert sorted(estimates.areas("Manhattan", hoods)) == ["chelsea", "west-village"]
    assert (
        estimates.areas("Mars", hoods) is None and estimates.areas(None, hoods) is None
    )


def test_held_out_accuracy_in_the_pages_terms():
    h = estimates.held_out(
        {
            "heldout": {
                "rows": 3,
                "median_abs_error": 0.0953,
                "coverage": {"50": 0.49, "95": 0.947},
            }
        }
    )
    assert round(h["median_error_pct"], 1) == 10.0
    assert [c["nominal"] for c in h["coverage"]] == [50, 95]
    assert [c["share"] for c in h["coverage"]] == pytest.approx([49.0, 94.7])
    assert estimates.held_out({}) is None


def _client_with(tmp_path, write_estimates, estimate_row, hoods):
    root = tmp_path / "site"
    rows = [
        estimate_row(
            str(i),
            "",
            "latest",
            "b",
            "",
            hood,
            1.0,
            "2025-01-01",
            3000.0,
            3000.0,
            0.5,
            0,
        )
        for i, hood in enumerate(hoods)
    ]
    write_estimates(root, rows)
    return create_app(root).test_client()


def test_one_neighbourhood_shows_no_neighbourhood_choice(
    tmp_path, write_estimates, estimate_row
):
    client = _client_with(tmp_path, write_estimates, estimate_row, ["chelsea"] * 2)
    assert 'name="nb"' not in client.get("/listings").get_data(as_text=True)


def test_two_boroughs_offer_each_borough_as_a_choice(
    tmp_path, write_estimates, estimate_row
):
    client = _client_with(
        tmp_path,
        write_estimates,
        estimate_row,
        ["chelsea", "west-village", "williamsburg", "Williamsburg"],
    )
    html = client.get("/listings").get_data(as_text=True)
    assert '<optgroup label="Brooklyn">' in html
    assert '<option value="Brooklyn">All of Brooklyn (2)</option>' in html
    assert '<option value="West Village">West Village (1)</option>' in html
    brooklyn = client.get("/listings?nb=Brooklyn").get_data(as_text=True)
    assert _rows(brooklyn) == ["2", "3"]
    assert '<option value="Brooklyn" selected>' in brooklyn
    assert _rows(client.get("/listings?nb=Manhattan").get_data(as_text=True)) == [
        "0",
        "1",
    ]

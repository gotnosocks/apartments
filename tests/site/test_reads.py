import json

from apartments.site.web import create_app


def _app(site_root, research_file):
    app = create_app(site_root, research_data=research_file)
    app.config["TESTING"] = True
    return app.test_client()


def test_listing_page_logs_the_columns_it_reads(site_root, research_file, monkeypatch):
    monkeypatch.delenv("SITE_READS_LOG", raising=False)
    client = _app(site_root, research_file)
    assert client.get("/listings/a1").status_code == 200
    lines = [
        json.loads(x) for x in (site_root / "reads.jsonl").read_text().splitlines()
    ]
    page = next(x for x in lines if x["endpoint"] == "listing")
    assert page["status"] == 200
    assert "listings.contributions" in page["queried"]
    assert {"contributions", "inputs", "ask"} <= set(page["used"])


def test_static_files_and_zero_leave_no_log(site_root, research_file, monkeypatch):
    monkeypatch.setenv("SITE_READS_LOG", "0")
    client = _app(site_root, research_file)
    assert client.get("/listings/a1").status_code == 200
    assert not (site_root / "reads.jsonl").exists()

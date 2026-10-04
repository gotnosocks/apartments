"""Numbers and guidance that agree across pages (playtest round 2)."""

import json
import sqlite3

from apartments.site.research import render_markdown


def test_about_counts_the_listings_in_the_fit(client):
    html = " ".join(client.get("/about").get_data(as_text=True).split())
    assert "listings in the fit (the rest of the" in html or "learned from the" in html


def test_glossary_says_the_plus_minus_is_against_the_baseline(client):
    html = " ".join(client.get("/research/glossary").get_data(as_text=True).split())
    assert (
        "paired difference" in html
        and "within about two of these are a tie" not in html
    )
    assert "(0.67 for the usual 1,000 draws)" in html


def test_home_tile_names_the_neighbourhoods_available_now(client, site_root):
    db = sqlite3.connect(site_root / "current" / "site.sqlite")
    stats = json.loads(
        db.execute("SELECT value FROM meta WHERE key = 'stats'").fetchone()[0]
    )
    stats["neighbourhoods"] = {"Chelsea": 3, "West Village": 1}
    db.execute("UPDATE meta SET value = ? WHERE key = 'stats'", (json.dumps(stats),))
    db.commit()
    db.close()
    html = client.get("/").get_data(as_text=True)
    assert "Available now (Chelsea only)" in html


def test_plan_links_to_the_site_drop_the_tailnet_host():
    html, _ = render_markdown(
        "See [the frontier](http://thelio.tail3983e0.ts.net:8600/research) and "
        "http://example.com/x."
    )
    assert "ts.net" not in html and 'href="/research"' in html
    assert "http://example.com/x" in html
    bare, _ = render_markdown(
        "The site (http://thelio.tail3983e0.ts.net:8600/research) applies."
    )
    assert "ts.net" not in bare and "site:" not in bare


def test_tailnet_links_in_autolinks_and_titles():
    html, _ = render_markdown(
        "<http://thelio.example.ts.net:8600/r> and "
        '[x](http://thelio.example.ts.net:8500/research "t")'
    )
    assert 'href="/r"' in html and 'href="/research"' in html

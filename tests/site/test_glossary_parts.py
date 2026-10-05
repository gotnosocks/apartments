"""The glossary's renter section: the parts of an estimate (playtest round 2)."""


def test_glossary_lists_the_estimate_parts(client):
    html = client.get("/research/glossary").get_data(as_text=True)
    assert 'id="estimate-parts"' in html and 'id="part-market"' in html


def test_listing_breakdown_links_each_part_to_the_glossary(client):
    html = client.get("/listings/a1").get_data(as_text=True)
    assert "/research/glossary#part-" in html


def test_term_ids_are_valid_and_shared():
    from apartments.site.web import term_id

    assert term_id("building size") == "part-building-size"
    assert term_id("bedroom_market_curve") == "part-bedroom-market-curve"
    assert term_id("Unit label") == "part-unit-label" and " " not in term_id("a b")

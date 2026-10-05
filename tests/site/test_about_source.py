"""The About page says what the site is and how to cite it (playtest round 3a)."""


def test_about_has_a_source_line_without_personal_details(client):
    html = " ".join(client.get("/about").get_data(as_text=True).split())
    assert 'id="source"' in html and "A personal research project" in html
    assert "github.com" not in html.split('id="source"')[1].split("</section>")[0]
    assert "first seen" not in html and "from asks dated" in html

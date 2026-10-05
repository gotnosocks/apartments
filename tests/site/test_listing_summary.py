from apartments.site.summary import listing_summary


def part(term, usd, lower, upper):
    return {"term": term, "usd": usd, "lower": lower, "upper": upper}


ROW = {
    "estimate": 5000.0,
    "full_baths": 1,
    "half_baths": 0,
    "floor": 6,
    "elevator": "yes",
}


def test_names_the_building_and_the_clear_parts_largest_first():
    parts = [
        part("market", 4000, 3900, 4100),
        part("building", 700, 400, 1000),
        part("laundry", 150, 100, 200),
        part("facing", 60, 30, 90),
        part("doorman", 300, 200, 400),
        part("floor", 40, -10, 90),  # interval spans zero: not named
        part("size", -120, -150, -90),
        part("unit", 100, -200, 400),  # not clear: no unit sentence
    ]
    inputs = {
        "laundry=in_unit": 1.0,
        "doorman=full_time": 1.0,
        "looks onto a side street": 1.0,
        "looks onto the rear or a courtyard": 1.0,
        "log_sqft_vs_bedroom_median": -0.2,
    }
    text = " ".join(listing_summary(ROW, parts, inputs))
    assert text.startswith(
        "This listing is in a building that rents higher than its peers with the "
        "same features: the model adds about $700 a month for it."
    )
    assert (
        "The model prices it up for a full-time doorman; laundry in the unit; and "
        "windows onto the rear or a courtyard and a quiet side street." in text
    )
    assert "It prices it down for less space than usual." in text
    assert "floor" not in text and "apartment itself" not in text


def test_small_or_unstated_parts_are_left_out():
    parts = [
        part("building", 10, 5, 15),  # clear, but under the size floor
        part("laundry", -60, -80, -40),  # laundry not stated
        part("doorman", -50, -70, -30),  # doorman not stated
        part("unit", -400, -600, -200),
        part("elevator", -300, -400, -200),
    ]
    inputs = {"laundry=unknown": 1.0, "doorman=unspecified": 1.0, "elevator=no": 1.0}
    row = dict(ROW, elevator="no")
    text = listing_summary(row, parts, inputs)
    assert text == [
        "Its building rents in line with its peers with the same features.",
        (
            "The apartment itself has rented below what its features and building "
            "predict, going by its other listings."
        ),
        "It prices it down for no elevator.",
    ]


def test_phrases_follow_the_models_inputs():
    clear = part("x", 0, 0, 0)

    def words(term, inputs, row=None, sign=1):
        parts = [
            dict(clear, term=term, usd=200 * sign, lower=100 * sign, upper=300 * sign)
        ]
        parts[0]["lower"], parts[0]["upper"] = sorted(
            (parts[0]["lower"], parts[0]["upper"])
        )
        return " ".join(listing_summary(dict(ROW, **(row or {})), parts, inputs))

    assert words(
        "description", {"text:renovated": 1, "text:states_fewer_bedrooms": 1}
    ) == (
        "The model prices it up for an ad that mentions a renovation and fewer "
        "bedrooms than listed."
    )
    # the floor is not known, or is the ground floor
    assert "floor" not in words("floor", {"floor_unknown": 1, "log_floor": 0.0})
    assert words("floor", {"log_floor": 0.0}, row={"floor": 0}).endswith(
        "a ground or lower floor."
    )
    assert words("windows", {"window_north": 1, "window_east": 1}).endswith(
        "north- and east-facing windows."
    )
    assert words("unit label", {"label:garden": 1}).endswith("a garden unit.")
    # every input of a grouped part is named, since any could be the cause
    assert words("building status", {"landmark": 1, "flood_zone_2015": 1}, sign=-1) == (
        "It prices it down for a landmark building and the 2015 flood-zone map."
    )
    # no elevator by the model's input, not the row's
    assert words("elevator", {"elevator=unknown": 1}, row={"elevator": "no"}) == ""
    # the size phrase follows the input's sign
    assert words("size", {"log_sqft_vs_bedroom_median": 0.3}, sign=-1).endswith(
        "more space than usual."
    )


def test_an_unsure_building_is_not_called_in_line():
    parts = [part("building", 40, -900, 980)]
    assert listing_summary(ROW, parts, {}) == [
        (
            "The model cannot yet tell whether its building rents above or below "
            "its peers with the same features."
        )
    ]
    assert listing_summary(dict(ROW, estimate=None), parts, {}) == []


def test_listing_page_shows_the_summary(client):
    html = client.get("/listings/a1").get_data(as_text=True)
    card = html[html.index('id="summary"') :]
    card = card[: card.index("</section>")]
    assert "What the model makes of it" in card and "95%" in card
    assert html.index('id="summary"') < html.index("What makes up the estimate")

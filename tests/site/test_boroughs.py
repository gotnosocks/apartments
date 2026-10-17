from apartments.site import boroughs


def test_a_borough_stands_for_its_neighbourhoods_once_there_are_two():
    counts = {"Chelsea": 3, "West Village": 2, "Williamsburg": 4}
    assert boroughs.grouped(counts) == {
        "Manhattan": {"Chelsea": 3, "West Village": 2},
        "Brooklyn": {"Williamsburg": 4},
    }
    assert boroughs.areas("Manhattan", counts) == ["Chelsea", "West Village"]
    assert boroughs.areas("Chelsea", counts) == ["Chelsea"]
    assert boroughs.areas("Queens", counts) is None
    assert boroughs.areas(None, counts) is None
    # one borough offers no whole-borough choice
    assert boroughs.areas("Manhattan", {"Chelsea": 3}) is None
    assert boroughs.areas("Other", {"Chelsea": 3, "Nowhere": 1}) is None
    assert boroughs.areas("Manhattan", {"Chelsea": 3, "Nowhere": 1}) is None


def test_scope_words_name_a_long_list_by_its_boroughs():
    assert boroughs.scope_words(["West Village", "Chelsea"]) == (
        "Chelsea and West Village"
    )
    assert boroughs.scope_words(list(boroughs.BOROUGH_OF)) == "Manhattan and Brooklyn"
    assert boroughs.scope_words([]) == "Chelsea"

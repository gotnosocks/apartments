import dataclasses

from rentfrontier import elegance, features, model


def config(name):
    return dataclasses.asdict(model.MODELS[name])


def test_every_model_and_feature_set_is_rated():
    assert all(elegance.model_complexity(config(n)) is not None for n in model.MODELS)
    assert [k for k in features.FEATURE_SETS if k not in elegance.FEATURES] == []


def test_structure_points():
    # Market trend, building and unit levels; the walk; the bedroom slope.
    assert elegance.model_complexity(config("m0-base")) == 3
    assert elegance.model_complexity(config("m5-nocurves")) == 6
    # Student-t units, then one point per building slope.
    assert elegance.model_complexity(config("m5-nocurves-tunits")) == 7
    assert elegance.model_complexity(config("m7-nocurves-bathfloor")) == 9
    assert elegance.model_complexity(config("m7-nocurves-floorslope")) == 10
    # Knot spacing changes how a term is parameterized, not what it says.
    assert elegance.model_complexity(
        config("m5-nocurves-walk12")
    ) == elegance.model_complexity(config("m5-nocurves"))


def test_an_unknown_option_or_set_is_unrated():
    assert elegance.model_complexity(config("m5-nocurves") | {"new_term": True}) is None
    assert elegance.model_complexity(config("m5-nocurves") | {"new_term": False}) == 6
    assert elegance.feature_complexity("unknown-v1") is None
    e = {"model": config("m7-nocurves-floorslope"), "feature_set": "unitfacing-v5"}
    assert elegance.complexity(e) == 19
    assert elegance.complexity(e | {"feature_set": "unknown-v1"}) is None
    # PyMC screens record only a model name.
    assert (
        elegance.complexity({"model": {"name": "nuts-hwalk"}, "feature_set": "x"})
        is None
    )

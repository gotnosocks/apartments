import pytest

from rentfrontier import drift
from rentfrontier import drift_building_phase_unitkn_cost as cost


def test_split_variant_separates_cost_tokens():
    rest, arms = cost.split_variant(("layrng", "bld_semi", "sv_gp_mo", "no_slow"))
    assert rest == ("layrng", "sv_gp_mo")
    assert arms == ("bld_semi", "no_slow")
    with pytest.raises(ValueError, match="one building step"):
        cost.split_variant(("bld_semi", "bld_annual"))
    with pytest.raises(ValueError, match="unknown variant"):
        cost.split_variant(("not_a_token",))


def test_groups_set_the_buildings_steps(monkeypatch):
    monkeypatch.setattr(
        drift,
        "groups_of",
        lambda d, which: [{"name": "building", "per_year": 4}],
    )
    assert cost.groups(None, ())[0]["per_year"] == 4
    assert cost.groups(None, ("bld_semi",))[0]["per_year"] == 2
    assert cost.groups(None, ("bld_annual",))[0]["per_year"] == 1


def test_no_slow_empties_the_slow_columns():
    s = drift.Settings()
    assert cost.settings_for(s, ()).slow_columns == s.slow_columns
    assert cost.settings_for(s, ("no_slow",)).slow_columns == ()


def test_spec_reads_through_to_ablate():
    assert cost.design is cost.ablate.design
    assert cost.NAME != cost.ablate.NAME


@pytest.mark.parametrize(
    "argv",
    [
        ["--variant", "layrng,bld_semi,no_slow", "--data", "D"],
        ["--variant=layrng,bld_semi,no_slow", "--data", "D"],
    ],
)
def test_main_run_takes_the_cost_tokens_out(monkeypatch, argv):
    from rentfrontier import drift_building_phase_unitkn_ablate as ablate

    seen = {}
    monkeypatch.setattr(drift, "main_run", lambda rest, **kw: seen.update(rest=rest))
    monkeypatch.setattr(ablate, "ACTIVE_VARIANT", ())
    monkeypatch.setattr(cost, "ACTIVE_COST", ())
    cost.main_run(argv)
    assert seen["rest"] == ["--data", "D"]
    assert ablate.ACTIVE_VARIANT == ("layrng",)
    assert cost.ACTIVE_COST == ("bld_semi", "no_slow")

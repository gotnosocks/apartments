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

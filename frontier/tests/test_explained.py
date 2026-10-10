import numpy as np
from rentfrontier import explained


def levels(rng, buildings=600, signal=0.6):
    x = rng.normal(size=(buildings, 2))
    sd2 = rng.uniform(0.001, 0.02, buildings)
    truth = signal * x[:, 0] * 0.1 + rng.normal(
        0, 0.1 * np.sqrt(1 - signal**2), buildings
    )
    level = truth + rng.normal(0, np.sqrt(sd2))
    return level, sd2, x


def test_a_real_family_beats_its_permutation_null():
    rng = np.random.default_rng(0)
    level, sd2, x = levels(rng)
    out = explained.screen(level, sd2, x, rng, permutations=20)
    assert out["explained"] > 0.2
    assert out["excess"] > 0.2
    assert out["explained"] > out["null_95"]


def test_noise_columns_explain_nothing_beyond_the_null():
    rng = np.random.default_rng(1)
    level, sd2, _ = levels(rng)
    noise = rng.normal(size=(len(level), 3))
    out = explained.screen(level, sd2, noise, rng, permutations=20)
    assert abs(out["excess"]) < 0.03
    assert out["explained"] < out["null_95"] + 0.02


def test_building_means_average_each_buildings_rows():
    values = np.array([[1.0], [3.0], [10.0]])
    out = explained.building_means(values, np.array([0, 0, 2]), 3)
    np.testing.assert_allclose(out[:, 0], [2.0, 0.0, 10.0])


def test_main_loads_the_run_once_for_every_candidate_set(monkeypatch, tmp_path):
    loads, scored = [], []
    monkeypatch.setattr(explained, "EXPLAINED_ROOT", tmp_path)
    monkeypatch.setattr(
        explained, "git", lambda *a: "" if a[0] == "status" else "abc1234"
    )
    monkeypatch.setattr(explained, "hardware", lambda: {})
    monkeypatch.setattr(
        explained, "load", lambda name: loads.append(name) or {"n": name}
    )
    monkeypatch.setattr(
        explained,
        "score",
        lambda run, cs: scored.append((run["n"], cs)) or {"families": {}},
    )
    (tmp_path / "r-done-abc1234").mkdir()
    (tmp_path / "r-done-abc1234" / "result.json").write_text("{}")
    explained.main(["r", "a", "b", "done"])
    assert loads == ["r"] and scored == [("r", "a"), ("r", "b")]
    assert (tmp_path / "r-a-abc1234" / "result.json").exists()
    loads.clear()
    explained.main(["r", "done"])
    assert loads == []

import numpy as np
import pytest
from rentfrontier import draws


def archive(tmp_path, chains=2, per_chain=7):
    rng = np.random.default_rng(0)
    stored = {
        "alpha": rng.normal(size=(chains, per_chain)).astype(np.float32),
        "walk": rng.normal(size=(chains, per_chain, 5, 4)).astype(np.float32),
        "beta": rng.normal(size=(chains, per_chain, 3)),
    }
    path = tmp_path / "posterior.npz"
    np.savez_compressed(
        path,
        units=np.array(["u0"]),
        **{f"kept/{k}": v for k, v in stored.items()},
    )
    return path, stored


@pytest.mark.parametrize("block", [1, 3, 20])
def test_read_gives_what_load_run_gives(tmp_path, block):
    path, stored = archive(tmp_path)
    whole = {
        k: v.reshape(14, *v.shape[2:]).astype(np.float64) for k, v in stored.items()
    }
    assert draws.shapes(path) == {k: v.shape for k, v in stored.items()}
    got = draws.read(path, block=block)
    assert set(got) == set(whole)
    for k in whole:
        assert got[k].dtype == np.float64
        np.testing.assert_array_equal(got[k], whole[k])
    idx = np.array([0, 2, 3, 9, 13])
    got = draws.read(
        path, {"walk", "alpha"}, idx, {"walk": lambda w: w[..., [1, 3]]}, block=block
    )
    assert set(got) == {"walk", "alpha"}
    np.testing.assert_array_equal(got["walk"], whole["walk"][idx][..., [1, 3]])
    np.testing.assert_array_equal(got["alpha"], whole["alpha"][idx])
    got = draws.read(path, {"walk"}, idx, dtype=None, block=block)
    assert got["walk"].dtype == np.float32
    np.testing.assert_array_equal(got["walk"], stored["walk"].reshape(14, 5, 4)[idx])


def test_read_refuses_draws_out_of_order_or_range(tmp_path):
    path, _ = archive(tmp_path)
    with pytest.raises(ValueError, match="increasing"):
        draws.read(path, {"alpha"}, [3, 1])
    with pytest.raises(ValueError, match="14 draws"):
        draws.read(path, {"alpha"}, [0, 14])

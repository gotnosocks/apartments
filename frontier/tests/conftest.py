import pytest

from rentfrontier import leaderboard


@pytest.fixture(autouse=True)
def _no_lot_registry(monkeypatch):
    """Paired SEs in tests are iid unless a test gives rows their lots: the
    real lot lookup loads the whole dataset and the NB8 registry."""
    monkeypatch.setattr(leaderboard, "_row_lots", lambda: None)

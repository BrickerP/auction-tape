import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def raw_rows():
    return json.loads((FIXTURES / "auctions.json").read_text())


@pytest.fixture
def curve_csv_path():
    return FIXTURES / "par_curve_2026.csv"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Tests must never hit the network."""
    import urllib.request

    def boom(*a, **k):
        raise AssertionError("network access attempted in tests")

    monkeypatch.setattr(urllib.request, "urlopen", boom)

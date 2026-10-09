import io
import json
import urllib.error
from datetime import date

import pytest

from auction_tape import fetch


def test_parse_curve_csv(curve_csv_path):
    closes = fetch.parse_curve_csv(curve_csv_path.read_text(encoding="utf-8-sig"))
    assert closes[date(2026, 10, 7)]["10-Year"] == 5.28
    assert closes[date(2026, 10, 7)]["2-Year"] == 4.77
    assert set(closes[date(2026, 10, 7)]) >= {"2-Year", "5-Year", "10-Year", "30-Year"}


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_fetch_raw_queries_notes_and_bonds(monkeypatch):
    seen = []

    def fake_urlopen(req, timeout=None, context=None):
        seen.append(req.full_url)
        return FakeResp(json.dumps([{"term": "x"}]).encode())

    monkeypatch.setattr(fetch.urllib.request, "urlopen", fake_urlopen)
    rows = fetch.fetch_raw(days=30)
    assert len(rows) == 2
    assert any("type=Note" in u and "days=30" in u for u in seen)
    assert any("type=Bond" in u for u in seen)


def test_get_bytes_retries_transient(monkeypatch):
    calls = {"n": 0}

    def flaky(req, timeout=None, context=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.URLError(ConnectionResetError("reset"))
        return FakeResp(b"ok")

    monkeypatch.setattr(fetch.urllib.request, "urlopen", flaky)
    monkeypatch.setattr(fetch.time, "sleep", lambda s: None)
    assert fetch.get_bytes("https://example.invalid/") == b"ok"
    assert calls["n"] == 2


def test_get_bytes_does_not_retry_http_errors(monkeypatch):
    def bad(req, timeout=None, context=None):
        raise urllib.error.HTTPError(req.full_url, 404, "nope", {}, None)

    monkeypatch.setattr(fetch.urllib.request, "urlopen", bad)
    with pytest.raises(urllib.error.HTTPError):
        fetch.get_bytes("https://example.invalid/")

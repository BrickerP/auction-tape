"""Download public data with the standard library only (no API keys needed).

* Auction results: TreasuryDirect's public JSON API.
* Closing yields (used to approximate a when-issued yield): the U.S. Treasury daily par yield curve CSV.
"""
from __future__ import annotations

import csv
import http.client
import io
import json
import os
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import date, datetime

API = "https://www.treasurydirect.gov/TA_WS/securities/auctioned"
CURVE_CSV = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/"
    "{year}/all?type=daily_treasury_yield_curve&field_tdr_date_value={year}&page&_format=csv"
)
USER_AGENT = "auction-tape/0.1 (+https://github.com/BrickerP/auction-tape)"

# Column in the par yield curve CSV for each auction term.
CURVE_COLUMNS = {
    "2-Year": "2 Yr", "3-Year": "3 Yr", "5-Year": "5 Yr", "7-Year": "7 Yr",
    "10-Year": "10 Yr", "20-Year": "20 Yr", "30-Year": "30 Yr",
}

_fallback_ctx: ssl.SSLContext | None = None


def _macos_roots_context() -> ssl.SSLContext | None:
    """Some Python builds ship a CA bundle that misses roots macOS trusts. Export the system roots and use them.

    Certificate verification stays on; we only widen the trust store to what the OS already trusts.
    """
    if sys.platform != "darwin":
        return None
    try:
        pem = subprocess.run(
            ["security", "find-certificate", "-a", "-p", "/System/Library/Keychains/SystemRootCertificates.keychain"],
            check=True, capture_output=True, text=True, timeout=20,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    if "BEGIN CERTIFICATE" not in pem:
        return None
    with tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False) as fh:
        fh.write(pem)
    ctx = ssl.create_default_context(cafile=fh.name)
    os.unlink(fh.name)
    return ctx


def _fallback_context() -> ssl.SSLContext | None:
    global _fallback_ctx
    if _fallback_ctx is None:
        try:
            import certifi  # type: ignore[import-not-found]

            _fallback_ctx = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            _fallback_ctx = _macos_roots_context()
    return _fallback_ctx


def _is_cert_error(err: BaseException) -> bool:
    reason = getattr(err, "reason", err)
    return isinstance(reason, ssl.SSLCertVerificationError)


def get_bytes(url: str, timeout: float = 30.0, retries: int = 2) -> bytes:
    """GET a URL, retrying transient connection drops (these public endpoints occasionally hang up)."""
    for attempt in range(retries + 1):
        try:
            return _get_once(url, timeout)
        except urllib.error.HTTPError:
            raise
        except (urllib.error.URLError, ConnectionError, TimeoutError, http.client.HTTPException) as e:
            if _is_cert_error(e) or attempt == retries:
                raise
            time.sleep(1.5 * (attempt + 1))
    raise AssertionError("unreachable")


def _get_once(url: str, timeout: float) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed https hosts
            return resp.read()
    except urllib.error.URLError as e:
        ctx = _fallback_context() if _is_cert_error(e) else None
        if ctx is None:
            raise
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:  # noqa: S310
            return resp.read()


def get_json(url: str, timeout: float = 30.0):
    return json.loads(get_bytes(url, timeout).decode("utf-8"))


def fetch_raw(days: int = 420, timeout: float = 30.0) -> list[dict]:
    """Return raw rows for coupon securities (Notes and Bonds) auctioned in the last ``days`` days."""
    rows: list[dict] = []
    for sec_type in ("Note", "Bond"):
        rows.extend(get_json(f"{API}?format=json&type={sec_type}&days={days}", timeout))
    return rows


def parse_curve_csv(text: str) -> dict[date, dict[str, float]]:
    """Parse the Treasury par yield curve CSV into {date: {'10-Year': 5.28, ...}}."""
    out: dict[date, dict[str, float]] = {}
    for row in csv.DictReader(io.StringIO(text)):
        raw_date = (row.get("Date") or "").strip()
        try:
            d = datetime.strptime(raw_date, "%m/%d/%Y").date()
        except ValueError:
            continue
        vals = {}
        for term, col in CURVE_COLUMNS.items():
            try:
                vals[term] = float(row.get(col) or "")
            except ValueError:
                pass
        out[d] = vals
    return out


def fetch_closes(years: set[int], timeout: float = 30.0) -> dict[date, dict[str, float]]:
    """Daily closing par yields by term for the given calendar years."""
    out: dict[date, dict[str, float]] = {}
    for y in sorted(years):
        out.update(parse_curve_csv(get_bytes(CURVE_CSV.format(year=y), timeout).decode("utf-8-sig")))
    return out

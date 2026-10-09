"""Demand score: how strong was this auction versus the previous auctions of the same term?

Three components, each a z-score against the previous ``window`` auctions of the same term (the auction itself is
never part of its own baseline):

* bid-to-cover (higher = stronger)
* indirect-bidder share of competitive awards (higher = stronger; this bucket includes foreign central banks)
* primary-dealer share (higher = weaker; dealers are the backstop buyer of last resort)

The score is the average of the available components. This is a transparent summary statistic, not a forecast.
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field

from .auctions import TERMS, Auction

MIN_HISTORY = 4
STRONG, SOFT = 1.0, -1.0


def zscore(x: float, history: list[float]) -> float | None:
    if len(history) < MIN_HISTORY:
        return None
    sd = statistics.pstdev(history)
    if sd == 0:
        return None
    return (x - statistics.fmean(history)) / sd


def label(score: float | None) -> str:
    if score is None:
        return "n/a"
    if score >= STRONG:
        return "strong"
    if score <= SOFT:
        return "soft"
    return "in line"


@dataclass
class Scored:
    auction: Auction
    z_btc: float | None = None
    z_indirect: float | None = None
    z_dealer: float | None = None  # already sign-flipped so higher = stronger demand
    score: float | None = None
    history_n: int = 0
    wi_yield: float | None = None
    wi_source: str | None = None  # "given" (--wi) or "close" (that day's Treasury closing par yield, an approximation)
    extra: dict = field(default_factory=dict)

    @property
    def label(self) -> str:
        return label(self.score)

    @property
    def tail_word(self) -> str | None:
        t = self.tail_bp
        if t is None:
            return None
        return "tail" if t > 0 else "stop-through" if t < 0 else "on the screws"

    @property
    def tail_bp(self) -> float | None:
        """High yield minus a when-issued yield, in bp. Positive = tail (weaker), negative = stop-through (stronger)."""
        if self.wi_yield is None:
            return None
        return round((self.auction.high_yield - self.wi_yield) * 100, 2)

    def to_dict(self) -> dict:
        r = lambda v: None if v is None else round(v, 2)  # noqa: E731
        return {
            **self.auction.to_dict(),
            "z_bid_to_cover": r(self.z_btc),
            "z_indirect": r(self.z_indirect),
            "z_dealer_inverted": r(self.z_dealer),
            "demand_score": r(self.score),
            "label": self.label,
            "history_n": self.history_n,
            "wi_yield": self.wi_yield,
            "wi_source": self.wi_source,
            "tail_bp": self.tail_bp,
            "tail_word": self.tail_word,
        }


def score_auctions(auctions: list[Auction], window: int = 12) -> list[Scored]:
    """Score every auction against the previous ``window`` auctions of its term. Input order does not matter."""
    out: list[Scored] = []
    for term in TERMS:
        series = sorted((a for a in auctions if a.term == term), key=lambda a: a.auction_date)
        for i, a in enumerate(series):
            hist = series[max(0, i - window):i]
            s = Scored(auction=a, history_n=len(hist))
            s.z_btc = zscore(a.bid_to_cover, [h.bid_to_cover for h in hist])
            if a.indirect_pct is not None:
                s.z_indirect = zscore(a.indirect_pct, [h.indirect_pct for h in hist if h.indirect_pct is not None])
            if a.dealer_pct is not None:
                z = zscore(a.dealer_pct, [h.dealer_pct for h in hist if h.dealer_pct is not None])
                s.z_dealer = None if z is None else -z
            parts = [z for z in (s.z_btc, s.z_indirect, s.z_dealer) if z is not None]
            s.score = round(statistics.fmean(parts), 3) if parts else None
            out.append(s)
    return out


def latest_per_term(scored: list[Scored]) -> list[Scored]:
    best: dict[str, Scored] = {}
    for s in scored:
        cur = best.get(s.auction.term)
        if cur is None or s.auction.auction_date >= cur.auction.auction_date:
            best[s.auction.term] = s
    return [best[t] for t in TERMS if t in best]


_WI_RE = re.compile(r"^\s*(\d{1,2})\s*[yY]\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*$")


def parse_wi(specs: list[str]) -> dict[str, float]:
    """Parse ['10Y=5.317', '30Y=5.41'] into {'10-Year': 5.317, '30-Year': 5.41}."""
    out: dict[str, float] = {}
    for spec in specs:
        m = _WI_RE.match(spec)
        if not m:
            raise ValueError(f"bad --wi value {spec!r}; expected something like 10Y=5.317")
        term = f"{int(m.group(1))}-Year"
        if term not in TERMS:
            raise ValueError(f"unsupported term in --wi {spec!r}; use one of {', '.join(t.split('-')[0] + 'Y' for t in TERMS)}")
        out[term] = float(m.group(2))
    return out


def apply_wi(scored: list[Scored], wi: dict[str, float]) -> None:
    """Attach when-issued yields to the most recent auction of each term only."""
    for s in latest_per_term(scored):
        if s.auction.term in wi:
            s.wi_yield = wi[s.auction.term]
            s.wi_source = "given"


def apply_close_wi(scored: list[Scored], closes: dict) -> None:
    """Approximate the when-issued yield with that day's closing par yield for terms without an explicit --wi.

    ``closes`` maps date -> {term: yield}. The close is taken a few hours after the 1pm ET auction and is a par
    (not when-issued) yield, so treat the result as a rough read, not the official tail.
    """
    for s in latest_per_term(scored):
        if s.wi_yield is not None:
            continue
        y = closes.get(s.auction.auction_date, {}).get(s.auction.term)
        if y is not None:
            s.wi_yield = y
            s.wi_source = "close"

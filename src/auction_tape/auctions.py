"""Parse TreasuryDirect rows into a small, typed record."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date

TERMS = ["2-Year", "3-Year", "5-Year", "7-Year", "10-Year", "20-Year", "30-Year"]

# Raw fields we actually use (also the fields kept in the test fixture).
RAW_FIELDS = [
    "cusip", "term", "type", "tips", "floatingRate", "reopening", "auctionDate", "issueDate",
    "interestRate", "highYield", "averageMedianYield", "bidToCoverRatio", "offeringAmount",
    "totalAccepted", "competitiveAccepted", "directBidderAccepted", "indirectBidderAccepted",
    "primaryDealerAccepted",
]


@dataclass
class Auction:
    term: str
    auction_date: date
    cusip: str
    reopening: bool
    coupon: float | None
    high_yield: float
    avg_yield: float | None
    bid_to_cover: float
    offering_bn: float | None
    accepted_bn: float | None
    direct_pct: float | None
    indirect_pct: float | None
    dealer_pct: float | None

    @property
    def high_minus_avg_bp(self) -> float | None:
        """Gap between the stop-out (high) yield and the average yield, in bp: how dispersed the bids were."""
        if self.avg_yield is None:
            return None
        return round((self.high_yield - self.avg_yield) * 100, 2)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["auction_date"] = self.auction_date.isoformat()
        d["high_minus_avg_bp"] = self.high_minus_avg_bp
        return d


def _f(value) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _share(part, whole) -> float | None:
    p, w = _f(part), _f(whole)
    if p is None or w is None or w <= 0:
        return None
    return round(p / w * 100, 2)


def parse_row(row: dict) -> Auction | None:
    """Return an Auction for a completed, fixed-rate, nominal coupon auction; otherwise None."""
    if row.get("tips") == "Yes" or row.get("floatingRate") == "Yes":
        return None
    term = row.get("term")
    if term not in TERMS:
        return None
    high, btc = _f(row.get("highYield")), _f(row.get("bidToCoverRatio"))
    if high is None or btc is None or not row.get("auctionDate"):
        return None  # announced but not yet auctioned
    comp = row.get("competitiveAccepted")
    bn = lambda v: None if _f(v) is None else round(_f(v) / 1e9, 3)  # noqa: E731
    return Auction(
        term=term,
        auction_date=date.fromisoformat(row["auctionDate"][:10]),
        cusip=row.get("cusip", ""),
        reopening=row.get("reopening") == "Yes",
        coupon=_f(row.get("interestRate")),
        high_yield=high,
        avg_yield=_f(row.get("averageMedianYield")),
        bid_to_cover=btc,
        offering_bn=bn(row.get("offeringAmount")),
        accepted_bn=bn(row.get("totalAccepted")),
        direct_pct=_share(row.get("directBidderAccepted"), comp),
        indirect_pct=_share(row.get("indirectBidderAccepted"), comp),
        dealer_pct=_share(row.get("primaryDealerAccepted"), comp),
    )


def parse_rows(rows: list[dict]) -> list[Auction]:
    out = [a for a in (parse_row(r) for r in rows) if a is not None]
    out.sort(key=lambda a: (a.term, a.auction_date))
    return out

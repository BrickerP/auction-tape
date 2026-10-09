from datetime import date

from auction_tape.auctions import parse_row, parse_rows


def test_parse_rows_keeps_completed_nominal_coupons(raw_rows):
    auctions = parse_rows(raw_rows)
    assert len(auctions) == 98
    assert {a.term for a in auctions} == {"2-Year", "3-Year", "5-Year", "7-Year", "10-Year", "20-Year", "30-Year"}


def test_parse_row_fields_and_shares(raw_rows):
    row = next(r for r in raw_rows if r["term"] == "10-Year" and r["auctionDate"].startswith("2026-10-07"))
    a = parse_row(row)
    assert a.auction_date == date(2026, 10, 7)
    assert a.reopening is True
    assert a.high_yield == 5.3
    assert a.bid_to_cover == 2.77
    assert a.offering_bn == 39.0
    assert a.indirect_pct == 80.34
    assert a.dealer_pct == 2.54
    assert a.direct_pct == 17.12
    assert a.high_minus_avg_bp == 4.5


def test_parse_row_skips_tips_frn_bills_and_unauctioned(raw_rows):
    base = dict(raw_rows[0])
    assert parse_row({**base, "tips": "Yes"}) is None
    assert parse_row({**base, "floatingRate": "Yes"}) is None
    assert parse_row({**base, "term": "13-Week"}) is None
    assert parse_row({**base, "highYield": ""}) is None
    assert parse_row({**base, "bidToCoverRatio": None}) is None


def test_missing_competitive_gives_none_shares(raw_rows):
    a = parse_row({**raw_rows[0], "competitiveAccepted": ""})
    assert a.indirect_pct is None and a.dealer_pct is None

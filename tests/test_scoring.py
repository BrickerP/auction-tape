from datetime import date

import pytest

from auction_tape.auctions import Auction, parse_rows
from auction_tape.scoring import (
    Scored, apply_close_wi, apply_wi, label, latest_per_term, parse_wi, score_auctions, zscore,
)


def mk(day, btc, ind=60.0, dlr=15.0, term="10-Year", hy=4.5):
    return Auction(term, date(2026, 1, 1).replace(day=day), "X", False, 4.0, hy, hy - 0.02, btc, 40, 40, 20, ind, dlr)


def test_zscore_needs_history_and_spread():
    assert zscore(3.0, [2.0, 2.0, 2.0, 2.0]) is None
    assert zscore(3.0, [1.0, 2.0, 3.0]) is None
    assert zscore(3.0, [1.0, 2.0, 3.0, 2.0]) == pytest.approx(1.0 / 0.7071, rel=1e-3)


def test_labels():
    assert label(None) == "n/a"
    assert label(1.2) == "strong"
    assert label(-1.0) == "soft"
    assert label(0.3) == "in line"


def test_auction_is_not_in_its_own_baseline_and_window_respected():
    series = [mk(d, 2.5 + (d % 2) * 0.1) for d in range(1, 20)] + [mk(25, 3.5, ind=80, dlr=5)]
    scored = score_auctions(series, window=12)
    last = latest_per_term(scored)[0]
    assert last.history_n == 12
    assert last.score > 2  # far above every baseline component
    assert last.label == "strong"
    assert scored[0].score is None  # first auction has no history


def test_dealer_share_is_inverted():
    series = [mk(d, 2.5 + (d % 2) * 0.1, dlr=15 + (d % 3)) for d in range(1, 13)] + [mk(20, 2.55, dlr=40)]
    last = latest_per_term(score_auctions(series))[0]
    assert last.z_dealer < 0  # heavy dealer take = weak


def test_fixture_scores_latest_10y(raw_rows):
    latest = {s.auction.term: s for s in latest_per_term(score_auctions(parse_rows(raw_rows)))}
    ten = latest["10-Year"]
    assert ten.auction.auction_date == date(2026, 10, 7)
    assert ten.history_n == 12
    assert ten.score == pytest.approx(2.37, abs=0.01)
    assert ten.label == "strong"


def test_parse_wi():
    assert parse_wi(["10Y=5.317", " 30y = 5.41 "]) == {"10-Year": 5.317, "30-Year": 5.41}
    with pytest.raises(ValueError):
        parse_wi(["10=5"])
    with pytest.raises(ValueError):
        parse_wi(["4Y=5"])


def test_tail_and_stop_through():
    s = Scored(auction=mk(5, 2.5, hy=4.50))
    s.wi_yield = 4.48
    assert s.tail_bp == 2.0 and s.tail_word == "tail"
    s.wi_yield = 4.515
    assert s.tail_bp == -1.5 and s.tail_word == "stop-through"
    s.wi_yield = 4.50
    assert s.tail_word == "on the screws"


def test_apply_wi_only_latest_and_given_beats_close():
    series = [mk(d, 2.5) for d in (1, 2, 3)]
    scored = score_auctions(series)
    apply_wi(scored, {"10-Year": 4.49})
    apply_close_wi(scored, {date(2026, 1, 3): {"10-Year": 4.40}})
    by_day = {s.auction.auction_date.day: s for s in scored}
    assert by_day[3].wi_yield == 4.49 and by_day[3].wi_source == "given"
    assert by_day[1].wi_yield is None


def test_apply_close_wi():
    scored = score_auctions([mk(d, 2.5) for d in (1, 2, 3)])
    apply_close_wi(scored, {date(2026, 1, 3): {"10-Year": 4.47}})
    last = latest_per_term(scored)[0]
    assert last.wi_source == "close" and last.tail_bp == 3.0

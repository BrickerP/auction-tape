from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path

from . import __version__
from .auctions import TERMS, parse_rows
from .fetch import fetch_closes, fetch_raw
from .render import dashboard_html, markdown, text_table
from .scoring import apply_close_wi, apply_wi, latest_per_term, parse_wi, score_auctions


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="auction-tape",
        description="Score U.S. Treasury note/bond auctions for demand against their own history.",
    )
    p.add_argument("--days", type=int, default=420, help="calendar days of auction history to fetch (default 420)")
    p.add_argument("--window", type=int, default=12, help="previous same-term auctions used as the baseline (default 12)")
    p.add_argument("--terms", default="2,5,10,30", help="comma list to show, e.g. 2,10,30, or 'all' (default: 2,5,10,30)")
    p.add_argument("--wi", action="append", default=[], metavar="10Y=5.317",
                   help="when-issued yield for the latest auction of a term, to print tail/stop-through (repeatable)")
    p.add_argument("--approx-wi", action="store_true",
                   help="for terms without --wi, approximate the WI yield with that day's Treasury closing par yield")
    p.add_argument("--closes-file", metavar="PATH",
                   help="read the Treasury daily par yield curve CSV from a file instead of the network (with --approx-wi)")
    p.add_argument("--from-file", metavar="PATH", help="read raw TreasuryDirect JSON from a file instead of the network")
    p.add_argument("--save-raw", metavar="PATH", help="also save the raw JSON that was fetched")
    p.add_argument("--json", action="store_true", help="print the scored latest auctions as JSON")
    p.add_argument("--md", action="store_true", help="print a Markdown table instead of the text table")
    p.add_argument("-o", "--output", metavar="PATH", help="write the HTML dashboard here")
    p.add_argument("--open", action="store_true", help="open the dashboard in a browser (needs -o)")
    p.add_argument("--timeout", type=float, default=30.0)
    p.add_argument("--version", action="version", version=f"auction-tape {__version__}")
    return p


def _wanted_terms(spec: str) -> set[str]:
    if not spec.strip() or spec.strip().lower() == "all":
        return set(TERMS)
    want = set()
    for tok in spec.split(","):
        tok = tok.strip().upper().rstrip("Y")
        if not tok.isdigit() or f"{int(tok)}-Year" not in TERMS:
            raise SystemExit(f"auction-tape: unknown term {tok!r}; choose from {', '.join(t.split('-')[0] for t in TERMS)}")
        want.add(f"{int(tok)}-Year")
    return want


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        wi = parse_wi(args.wi)
        wanted = _wanted_terms(args.terms)
    except ValueError as e:
        print(f"auction-tape: {e}", file=sys.stderr)
        return 2
    try:
        if args.from_file:
            raw = json.loads(Path(args.from_file).read_text())
        else:
            raw = fetch_raw(args.days, args.timeout)
    except Exception as e:  # network or file problems: one clear line, non-zero exit
        print(f"auction-tape: could not load auction data: {e}", file=sys.stderr)
        return 1
    if args.save_raw:
        Path(args.save_raw).write_text(json.dumps(raw))
    auctions = [a for a in parse_rows(raw) if a.term in wanted]
    if not auctions:
        print("auction-tape: no completed auctions found in the data", file=sys.stderr)
        return 1
    scored = score_auctions(auctions, window=args.window)
    apply_wi(scored, wi)
    if args.approx_wi:
        from .fetch import parse_curve_csv

        try:
            if args.closes_file:
                closes = parse_curve_csv(Path(args.closes_file).read_text(encoding="utf-8-sig"))
            else:
                years = {s.auction.auction_date.year for s in latest_per_term(scored)}
                closes = fetch_closes(years, args.timeout)
        except Exception as e:  # the score still works without closes
            print(f"auction-tape: could not load closing yields, skipping tail: {e}", file=sys.stderr)
        else:
            apply_close_wi(scored, closes)
    if args.output:
        Path(args.output).write_text(dashboard_html(scored, window=args.window), encoding="utf-8")
        print(f"wrote {args.output}", file=sys.stderr)
        if args.open:
            webbrowser.open(Path(args.output).resolve().as_uri())
    if args.json:
        print(json.dumps([s.to_dict() for s in latest_per_term(scored)], indent=2))
    elif args.md:
        print(markdown(scored))
    else:
        print(text_table(scored))
    return 0

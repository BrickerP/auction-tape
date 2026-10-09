"""Text, Markdown and single-file HTML renderers."""
from __future__ import annotations

import html
from datetime import datetime, timezone

from .auctions import TERMS
from .scoring import Scored, latest_per_term


def _n(v, fmt="{:.2f}", dash="–"):
    return dash if v is None else fmt.format(v)


def _sgn(v, fmt="{:+.2f}", dash="–"):
    return dash if v is None else fmt.format(v)


def text_table(scored: list[Scored]) -> str:
    head = f"{'term':8} {'auction':10} {'high%':>7} {'btc':>5} {'indir%':>7} {'dealer%':>8} {'score':>6}  {'read':8} {'tail bp':>8}"
    lines = [head, "-" * len(head)]
    for s in latest_per_term(scored):
        a = s.auction
        lines.append(
            f"{a.term:8} {a.auction_date.isoformat():10} {a.high_yield:7.3f} {a.bid_to_cover:5.2f} "
            f"{_n(a.indirect_pct, '{:.1f}'):>7} {_n(a.dealer_pct, '{:.1f}'):>8} {_sgn(s.score):>6}  {s.label:8} {_sgn(s.tail_bp, '{:+.1f}'):>8}"
        )
    return "\n".join(lines)


def markdown(scored: list[Scored]) -> str:
    rows = ["| Term | Auction | High yield | Bid-to-cover | Indirect % | Dealer % | Demand score | Read | Tail (bp) |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |"]
    for s in latest_per_term(scored):
        a = s.auction
        rows.append(
            f"| {a.term} | {a.auction_date} | {a.high_yield:.3f}% | {a.bid_to_cover:.2f} | {_n(a.indirect_pct, '{:.1f}')} | "
            f"{_n(a.dealer_pct, '{:.1f}')} | {_sgn(s.score)} | {s.label} | {_sgn(s.tail_bp, '{:+.1f}')} |"
        )
    return "\n".join(rows)


COLORS = {"strong": "#3fb950", "in line": "#8b949e", "soft": "#f85149", "n/a": "#6e7681"}


def _spark(series: list[Scored], w=220, h=44) -> str:
    vals = [s.score for s in series][-12:]
    if not vals:
        return ""
    bar, gap = (w - 4) / max(len(vals), 12), 2
    mid = h / 2
    scale = (h / 2 - 3) / max(2.0, max(abs(v) for v in vals if v is not None) if any(v is not None for v in vals) else 2.0)
    parts = [f'<line x1="0" x2="{w}" y1="{mid}" y2="{mid}" stroke="#30363d" stroke-width="1"/>']
    for i, v in enumerate(vals):
        x = 2 + i * bar
        if v is None:
            parts.append(f'<rect x="{x:.1f}" y="{mid - 1}" width="{bar - gap:.1f}" height="2" fill="#6e7681"/>')
            continue
        hh = max(1.5, abs(v) * scale)
        y = mid - hh if v >= 0 else mid
        c = COLORS["strong"] if v >= 1 else COLORS["soft"] if v <= -1 else COLORS["in line"]
        last = ' stroke="#e6edf3" stroke-width="1"' if i == len(vals) - 1 else ""
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar - gap:.1f}" height="{hh:.1f}" rx="1.5" fill="{c}"{last}/>')
    return f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="demand score history">{"".join(parts)}</svg>'


def dashboard_html(scored: list[Scored], window: int = 12) -> str:
    esc = html.escape
    latest = latest_per_term(scored)
    cards = []
    for s in latest:
        a = s.auction
        series = sorted((x for x in scored if x.auction.term == a.term), key=lambda x: x.auction.auction_date)
        col = COLORS[s.label]
        tail = ""
        if s.tail_bp is not None:
            src = "WI" if s.wi_source == "given" else "close≈WI"
            tail = f'<div class="kv"><span>vs {src} {s.wi_yield:.3f}%</span><b>{s.tail_bp:+.1f} bp {s.tail_word}</b></div>'
        cards.append(f"""
<section class="card">
  <header><h2>{esc(a.term)}</h2><span class="badge" style="background:{col}22;color:{col};border-color:{col}66">{esc(s.label)} {esc(_sgn(s.score))}</span></header>
  <div class="big">{a.high_yield:.3f}<small>%</small></div>
  <div class="sub">{esc(a.auction_date.isoformat())} · {'reopening' if a.reopening else 'new issue'} · ${_n(a.offering_bn, '{:.0f}')}bn</div>
  <div class="kv"><span>bid-to-cover</span><b>{a.bid_to_cover:.2f} <i>z {esc(_sgn(s.z_btc))}</i></b></div>
  <div class="kv"><span>indirect share</span><b>{esc(_n(a.indirect_pct, '{:.1f}'))}% <i>z {esc(_sgn(s.z_indirect))}</i></b></div>
  <div class="kv"><span>dealer share</span><b>{esc(_n(a.dealer_pct, '{:.1f}'))}% <i>z {esc(_sgn(None if s.z_dealer is None else -s.z_dealer))}</i></b></div>
  <div class="kv"><span>high − avg yield</span><b>{esc(_n(a.high_minus_avg_bp, '{:.1f}'))} bp</b></div>
  {tail}
  <div class="spark">{_spark(series)}<span>last {min(12, len(series))} scores</span></div>
</section>""")
    recent = sorted(scored, key=lambda s: s.auction.auction_date, reverse=True)[:24]
    trs = []
    for s in recent:
        a = s.auction
        col = COLORS[s.label]
        trs.append(
            f"<tr><td>{a.auction_date}</td><td>{esc(a.term)}</td><td class=r>{a.high_yield:.3f}</td><td class=r>{a.bid_to_cover:.2f}</td>"
            f"<td class=r>{esc(_n(a.indirect_pct, '{:.1f}'))}</td><td class=r>{esc(_n(a.dealer_pct, '{:.1f}'))}</td>"
            f"<td class=r style=\"color:{col}\">{esc(_sgn(s.score))}</td><td style=\"color:{col}\">{esc(s.label)}</td></tr>"
        )
    asof = latest[0].auction.auction_date if latest else None
    newest = max((s.auction.auction_date for s in scored), default=asof)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>auction-tape · Treasury auction demand</title>
<style>
:root{{color-scheme:dark}}
body{{margin:0;background:#0d1117;color:#e6edf3;font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif}}
main{{max-width:1120px;margin:0 auto;padding:28px 20px 40px}}
h1{{font-size:24px;margin:0 0 4px}} .lede{{color:#8b949e;margin:0 0 22px;max-width:760px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:14px}}
.card{{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:14px 16px}}
.card header{{display:flex;justify-content:space-between;align-items:center}} h2{{font-size:15px;margin:0}}
.badge{{font-size:12px;border:1px solid;border-radius:999px;padding:2px 9px;font-weight:600}}
.big{{font-size:34px;font-weight:700;margin:8px 0 0;letter-spacing:-.5px}} .big small{{font-size:18px;color:#8b949e}}
.sub{{color:#8b949e;font-size:12px;margin-bottom:10px}}
.kv{{display:flex;justify-content:space-between;padding:3px 0;border-top:1px solid #21262d;font-size:13px}} .kv span{{color:#8b949e}} .kv i{{color:#6e7681;font-style:normal;font-size:11px;margin-left:4px}}
.spark{{margin-top:8px}} .spark span{{display:block;color:#6e7681;font-size:11px}}
h3{{margin:28px 0 8px;font-size:15px}}
table{{width:100%;border-collapse:collapse;font-size:13px}} th,td{{padding:5px 8px;border-bottom:1px solid #21262d;text-align:left}} th{{color:#8b949e;font-weight:600}} .r{{text-align:right;font-variant-numeric:tabular-nums}}
footer{{color:#6e7681;font-size:12px;margin-top:24px}}
</style></head><body><main>
<h1>auction-tape</h1>
<p class="lede">How strong was demand at the latest U.S. Treasury note and bond auctions, compared with the previous {window} auctions of the same term? Score = average z-score of bid-to-cover, indirect share and (inverted) dealer share. Tail = high yield minus when-issued yield (close≈WI: that day's Treasury closing par yield, a rough proxy). Latest auction in data: {esc(str(newest))}.</p>
<div class="grid">{''.join(cards)}</div>
<h3>Recent auctions</h3>
<table><thead><tr><th>Date</th><th>Term</th><th class=r>High %</th><th class=r>BTC</th><th class=r>Indirect %</th><th class=r>Dealer %</th><th class=r>Score</th><th>Read</th></tr></thead><tbody>{''.join(trs)}</tbody></table>
<footer>Data: TreasuryDirect public auction results. Generated {stamp}. Informational only, not financial advice.</footer>
</main></body></html>"""

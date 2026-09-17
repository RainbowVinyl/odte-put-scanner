#!/usr/bin/env python3
"""
0DTE SPX Improved Put Credit Spread Scanner

Default book:
  09:00-09:05 CT
  short ~20-delta or expected-move put
  $10 wide (max $20)
  sell at bid
  GTC cover at 75% of credit (keep 25%)
  hold losers to cash settle
  skip events / gap-downs / VIX1D>VIX / cheap credits

Usage:
  python3 scanner.py --chain chain.example.json
  python3 scanner.py --chain chain.json --width 10 --contracts 1
  python3 scanner.py --live --chain chain.json
  python3 scanner.py --atm --chain chain.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=5d"
UA = "Mozilla/5.0 0dte-put-scanner/1.0"


# ---------------------------------------------------------------------------
# models
# ---------------------------------------------------------------------------

@dataclass
class Put:
    strike: float
    bid: float
    ask: float
    delta: float | None = None

    @property
    def mid(self) -> float:
        if self.bid <= 0 and self.ask <= 0:
            return 0.0
        if self.bid <= 0:
            return self.ask
        if self.ask <= 0:
            return self.bid
        return (self.bid + self.ask) / 2.0


@dataclass
class Market:
    spot: float | None = None
    prior_close: float | None = None
    vix: float | None = None
    vix1d: float | None = None
    event: str = ""
    expiration: str = ""
    asof: str = ""
    puts: list[Put] = field(default_factory=list)

    @property
    def gap_pct(self) -> float | None:
        if self.spot is None or self.prior_close in (None, 0):
            return None
        return (self.spot - self.prior_close) / self.prior_close * 100.0


@dataclass
class Cfg:
    width: int = 10
    contracts: int = 1
    friction: float = 0.20
    min_credit_pct_of_width: float = 0.15
    max_vertical_width_ok: float = 0.30
    gap_skip_pct: float = -0.6
    target_pct: float = 0.25
    delta_target: float = 0.20
    delta_band: float = 0.08
    timezone: str = "America/Chicago"
    entry_window: str = "09:00-09:05 CT"
    width_max_allowed: int = 20


@dataclass
class Ticket:
    status: str
    book: str
    skip: list[str]
    short: Put | None
    long: Put | None
    width: int
    contracts: int
    credit_bid: float
    credit_mid: float
    haircut_credit: float
    target_debit: float
    keep_usd: float
    max_risk_usd: float
    credit_pct: float
    vertical_width: float
    short_why: str
    liquidity: str
    loser_rule: str


# ---------------------------------------------------------------------------
# io
# ---------------------------------------------------------------------------

def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def load_cfg(path: Path | None, args: argparse.Namespace) -> Cfg:
    raw: dict[str, Any] = {}
    if path and path.exists():
        raw = load_json(path)
    cfg = Cfg(**{k: raw[k] for k in Cfg.__dataclass_fields__ if k in raw})
    if args.width:
        cfg.width = int(args.width)
    if args.contracts:
        cfg.contracts = int(args.contracts)
    return cfg


def load_market(chain_path: Path) -> Market:
    raw = load_json(chain_path)
    puts = [
        Put(
            strike=float(p["strike"]),
            bid=float(p.get("bid") or 0),
            ask=float(p.get("ask") or 0),
            delta=(float(p["delta"]) if p.get("delta") not in (None, "") else None),
        )
        for p in raw.get("puts", [])
    ]
    puts.sort(key=lambda x: x.strike, reverse=True)
    return Market(
        spot=_f(raw.get("spot")),
        prior_close=_f(raw.get("prior_close")),
        vix=_f(raw.get("vix")),
        vix1d=_f(raw.get("vix1d")),
        event=str(raw.get("event") or ""),
        expiration=str(raw.get("expiration") or ""),
        asof=str(raw.get("asof") or ""),
        puts=puts,
    )


def _f(v: Any) -> float | None:
    if v is None or v == "":
        return None
    return float(v)


def yahoo_last_and_prev(symbol: str) -> tuple[float | None, float | None]:
    url = YAHOO_CHART.format(sym=urllib.parse.quote(symbol, safe=""))
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
    except Exception:
        return None, None
    try:
        result = data["chart"]["result"][0]
        meta = result["meta"]
        last = meta.get("regularMarketPrice")
        prev = meta.get("chartPreviousClose") or meta.get("previousClose")
        closes = (result.get("indicators") or {}).get("quote", [{}])[0].get("close") or []
        closes = [c for c in closes if c is not None]
        if last is None and closes:
            last = closes[-1]
        if prev is None and len(closes) >= 2:
            prev = closes[-2]
        return (_f(last), _f(prev))
    except Exception:
        return None, None


def enrich_live(mkt: Market) -> Market:
    import urllib.parse  # local; used by yahoo helper via global later

    spot, prev = yahoo_last_and_prev("^GSPC")
    if spot:
        mkt.spot = spot
    if prev:
        mkt.prior_close = prev
    vix, _ = yahoo_last_and_prev("^VIX")
    if vix:
        mkt.vix = vix
    v1, _ = yahoo_last_and_prev("^VIX1D")
    if v1:
        mkt.vix1d = v1
    return mkt


# yahoo helper needs urllib.parse at module level
import urllib.parse  # noqa: E402


# ---------------------------------------------------------------------------
# scan logic
# ---------------------------------------------------------------------------

def expected_move(spot: float, vix1d: float | None, vix: float | None) -> float | None:
    """Rough 1-session expected move in points. Prefers VIX1D."""
    vol = vix1d if vix1d else vix
    if not vol or not spot:
        return None
    # VIX-style annual vol → 1-day move ≈ spot * vol/100 / sqrt(252)
    return spot * (vol / 100.0) / math.sqrt(252.0)


def pick_short(mkt: Market, cfg: Cfg, atm: bool) -> tuple[Put | None, str]:
    if not mkt.puts or mkt.spot is None:
        return None, "no chain or spot"

    if atm:
        put = min(mkt.puts, key=lambda p: abs(p.strike - mkt.spot))
        return put, f"ATM closest to spot {mkt.spot:.2f}"

    with_delta = [p for p in mkt.puts if p.delta is not None]
    if with_delta:
        # puts stored as negative or positive; use abs
        target = cfg.delta_target
        put = min(with_delta, key=lambda p: abs(abs(p.delta or 0) - target))
        d = abs(put.delta or 0)
        if abs(d - target) <= cfg.delta_band:
            return put, f"~{target:.0%} delta (actual {d:.2f})"

    em = expected_move(mkt.spot, mkt.vix1d, mkt.vix)
    if em:
        target_strike = mkt.spot - em
        put = min(mkt.puts, key=lambda p: abs(p.strike - target_strike))
        return put, f"expected-move strike (EM {em:.1f} pts → {target_strike:.1f})"

    # fallback: ~0.3% OTM as a crude 20-delta proxy
    target_strike = mkt.spot * 0.997
    put = min(mkt.puts, key=lambda p: abs(p.strike - target_strike))
    return put, f"fallback ~0.3% OTM proxy ({target_strike:.1f})"


def pick_long(mkt: Market, short: Put, width: int) -> Put | None:
    want = short.strike - width
    exact = [p for p in mkt.puts if abs(p.strike - want) < 0.01]
    if exact:
        return exact[0]
    # allow missing long quote: synthesize empty bid/ask so math still runs
    return Put(strike=want, bid=0.0, ask=0.0, delta=None)


def vertical_credit(short: Put, long: Put) -> tuple[float, float, float]:
    """Return credit_bid, credit_mid, quote_width on the vertical."""
    # sell short at bid, buy long at ask
    credit_bid = short.bid - (long.ask if long.ask > 0 else long.bid)
    credit_mid = short.mid - long.mid
    qwidth = (short.ask - short.bid) + (long.ask - long.bid)
    return credit_bid, credit_mid, qwidth


def skip_rules(mkt: Market, cfg: Cfg, event_dates: set[str], extra_event: str) -> list[str]:
    fails: list[str] = []
    event = extra_event or mkt.event
    today = datetime.now().date().isoformat()
    if event.strip():
        fails.append(f"event: {event.strip()}")
    if today in event_dates:
        fails.append(f"events.json skip date {today}")
    gap = mkt.gap_pct
    if gap is not None and gap <= cfg.gap_skip_pct:
        fails.append(f"gap {gap:.2f}% <= {cfg.gap_skip_pct}%")
    if mkt.vix1d is not None and mkt.vix is not None and mkt.vix1d > mkt.vix:
        fails.append(f"VIX1D {mkt.vix1d:.2f} > VIX {mkt.vix:.2f}")
    if not mkt.puts:
        fails.append("no 0DTE put chain")
    return fails


def build_ticket(mkt: Market, cfg: Cfg, atm: bool, event_dates: set[str], extra_event: str) -> Ticket:
    book = "BASELINE ATM" if atm else "IMPROVED"
    loser = (
        "flatten 12:00 CT if 25% not hit"
        if atm
        else "hold to cash settlement if 25% never prints"
    )
    skips = skip_rules(mkt, cfg, event_dates, extra_event)

    if cfg.width > cfg.width_max_allowed:
        skips.append(f"width {cfg.width} > max allowed {cfg.width_max_allowed}")

    short, why = pick_short(mkt, cfg, atm=atm)
    long = pick_long(mkt, short, cfg.width) if short else None

    credit_bid = credit_mid = haircut = target = keep = risk = pct = qwidth = 0.0
    liq = "N/A"

    if short and long:
        credit_bid, credit_mid, qwidth = vertical_credit(short, long)
        haircut = credit_bid - cfg.friction
        target = (1.0 - cfg.target_pct) * max(credit_bid, 0.0)
        keep = cfg.target_pct * max(credit_bid, 0.0) * 100 * cfg.contracts
        risk = (cfg.width - max(credit_bid, 0.0)) * 100 * cfg.contracts
        pct = (credit_bid / cfg.width) if cfg.width else 0.0
        liq = "WIDE" if qwidth > cfg.max_vertical_width_ok else "OK"
        if long.bid <= 0 and long.ask <= 0:
            skips.append(f"long {long.strike:.0f} missing quotes")
        if credit_bid <= 0:
            skips.append("credit bid <= 0 (check chain bids/asks)")
        if haircut < cfg.min_credit_pct_of_width * cfg.width:
            skips.append(
                f"haircut credit {haircut:.2f} < {cfg.min_credit_pct_of_width:.0%} of width"
            )
        if liq == "WIDE":
            skips.append(f"vertical quote width {qwidth:.2f} > {cfg.max_vertical_width_ok}")

    status = "NO TRADE" if skips or not short or not long else "TRADE"

    return Ticket(
        status=status,
        book=book,
        skip=skips,
        short=short,
        long=long,
        width=cfg.width,
        contracts=cfg.contracts,
        credit_bid=credit_bid,
        credit_mid=credit_mid,
        haircut_credit=haircut,
        target_debit=target,
        keep_usd=keep,
        max_risk_usd=risk,
        credit_pct=pct,
        vertical_width=qwidth,
        short_why=why,
        liquidity=liq,
        loser_rule=loser,
    )


def render(mkt: Market, cfg: Cfg, t: Ticket) -> str:
    gap = f"{mkt.gap_pct:.2f}%" if mkt.gap_pct is not None else "n/a"
    lines = [
        "=" * 64,
        "0DTE PUT SPREAD SCAN",
        "=" * 64,
        f"Status:        {t.status}",
        f"Book:          {t.book}",
        f"As-of:         {mkt.asof or datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"Window:        {cfg.entry_window}",
        f"Expiration:    {mkt.expiration or '0DTE today'}",
        f"SPX spot:      {mkt.spot if mkt.spot is not None else 'n/a'}",
        f"Prior close:   {mkt.prior_close if mkt.prior_close is not None else 'n/a'}",
        f"Gap:           {gap}",
        f"VIX / VIX1D:   {mkt.vix if mkt.vix is not None else 'n/a'} / {mkt.vix1d if mkt.vix1d is not None else 'n/a'}",
        f"Event:         {mkt.event or '(none in chain file)'}",
        f"Skip filter:   {'FAIL — ' + '; '.join(t.skip) if t.skip else 'PASS'}",
        "",
        "TICKET",
        "-" * 64,
    ]
    if t.short and t.long:
        lines += [
            f"Short put:     {t.short.strike:.0f}   bid {t.short.bid:.2f}  ask {t.short.ask:.2f}"
            + (f"  delta {t.short.delta}" if t.short.delta is not None else ""),
            f"Long put:      {t.long.strike:.0f}   bid {t.long.bid:.2f}  ask {t.long.ask:.2f}",
            f"Width / qty:   {t.width} / {t.contracts}",
            f"Why short:     {t.short_why}",
            f"Credit bid:    {t.credit_bid:.2f}",
            f"Credit mid:    {t.credit_mid:.2f}   (reference only)",
            f"After friction:{t.haircut_credit:.2f}  (friction {cfg.friction:.2f})",
            f"Credit % width:{t.credit_pct*100:.1f}%",
            f"Max risk $:    {t.max_risk_usd:,.2f}",
            f"25% target d:  {t.target_debit:.2f}",
            f"$ kept if hit: {t.keep_usd:,.2f}",
            f"Loser rule:    {t.loser_rule}",
            f"Liquidity:     {t.liquidity}  (vert quote width {t.vertical_width:.2f})",
            "",
            "GTC:",
            f"  BTC {t.short.strike:.0f}/{t.long.strike:.0f} 0DTE put vertical "
            f"@ {t.target_debit:.2f} GTC day-session",
        ]
    else:
        lines.append("No ticket — missing strikes or chain.")

    lines += [
        "",
        "SECOND ENTRY: NOT ARMED until first spread is closed >= 25%.",
        "",
        "DISCLAIMER",
        "Historical study stats are not a forecast. A 0DTE put spread can",
        "lose nearly the full width in a fast selloff. Size from max loss,",
        "not win rate. Use bid fills, not mid. Not financial advice.",
        "=" * 64,
    ]
    return "\n".join(lines)


def write_json_out(path: Path, mkt: Market, t: Ticket) -> None:
    payload = {
        "status": t.status,
        "book": t.book,
        "skip": t.skip,
        "spot": mkt.spot,
        "gap_pct": mkt.gap_pct,
        "vix": mkt.vix,
        "vix1d": mkt.vix1d,
        "short": t.short.strike if t.short else None,
        "long": t.long.strike if t.long else None,
        "credit_bid": t.credit_bid,
        "target_debit": t.target_debit,
        "keep_usd": t.keep_usd,
        "max_risk_usd": t.max_risk_usd,
        "loser_rule": t.loser_rule,
    }
    path.write_text(json.dumps(payload, indent=2))


# ---------------------------------------------------------------------------
# cli
# ---------------------------------------------------------------------------

def app_dir() -> Path:
    """Directory of the running program (source, zipapp, or frozen binary)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    argv0 = Path(sys.argv[0]).resolve()
    if argv0.exists():
        return argv0.parent if argv0.is_file() else argv0
    return Path(__file__).resolve().parent


def resolve_chain(explicit: str | None) -> Path | None:
    if explicit:
        return Path(explicit)
    here = app_dir()
    cwd = Path.cwd()
    for cand in (
        cwd / "chain.json",
        here / "chain.json",
        here / "chain.example.json",
        cwd / "chain.example.json",
    ):
        if cand.exists():
            return cand
    return None


def parse_args() -> argparse.Namespace:
    here = app_dir()
    p = argparse.ArgumentParser(description="0DTE improved put-spread scanner")
    p.add_argument("--chain", help="JSON put chain. Default: ./chain.json or bundled example")
    p.add_argument("--config", default=str(here / "config.json"))
    p.add_argument("--events", default=str(here / "events.json"))
    p.add_argument("--width", type=int)
    p.add_argument("--contracts", type=int)
    p.add_argument("--event", default="", help="override event name, e.g. FOMC")
    p.add_argument("--live", action="store_true", help="overlay Yahoo ^GSPC/^VIX/^VIX1D")
    p.add_argument("--atm", action="store_true", help="scan BASELINE ATM instead of 20d/EM")
    p.add_argument("--out", help="write JSON ticket to this path")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    chain_path = resolve_chain(args.chain)
    if chain_path is None or not chain_path.exists():
        print(
            "chain file not found. Put quotes in chain.json next to the program\n"
            "or pass --chain /path/to/chain.json",
            file=sys.stderr,
        )
        return 2
    print(f"[scanner] chain: {chain_path}", file=sys.stderr)

    cfg = load_cfg(Path(args.config) if args.config else None, args)
    mkt = load_market(chain_path)

    event_dates: set[str] = set()
    ev_path = Path(args.events)
    if ev_path.exists():
        event_dates = set(load_json(ev_path).get("skip_dates") or [])

    if args.live:
        mkt = enrich_live(mkt)
    if args.event:
        mkt.event = args.event

    ticket = build_ticket(mkt, cfg, atm=args.atm, event_dates=event_dates, extra_event=args.event)
    print(render(mkt, cfg, ticket))
    if args.out:
        write_json_out(Path(args.out), mkt, ticket)
    return 0 if ticket.status == "TRADE" else 1


if __name__ == "__main__":
    raise SystemExit(main())

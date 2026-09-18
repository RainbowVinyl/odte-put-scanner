"""Optional option-tape fetchers. All are opt-in; file chain stays the default."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from typing import Any

UA = "Mozilla/5.0 0dte-put-scanner/1.1"


def http_json(url: str, headers: dict[str, str] | None = None, timeout: int = 12) -> dict[str, Any]:
    h = {"User-Agent": UA, "Accept": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def today_iso() -> str:
    return date.today().isoformat()


def _put_rows(puts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in puts:
        try:
            strike = float(p.get("strike") or p.get("strike_price") or 0)
        except (TypeError, ValueError):
            continue
        if strike <= 0:
            continue
        bid = float(p.get("bid") or p.get("last_quote", {}).get("bid", 0) or 0)
        ask = float(p.get("ask") or p.get("last_quote", {}).get("ask", 0) or 0)
        greeks = p.get("greeks") or p.get("day") or {}
        delta = p.get("delta")
        if delta is None:
            delta = greeks.get("delta")
        try:
            delta_f = float(delta) if delta not in (None, "") else None
        except (TypeError, ValueError):
            delta_f = None
        if bid <= 0 and ask <= 0:
            continue
        out.append({"strike": strike, "bid": bid, "ask": ask, "delta": delta_f})
    out.sort(key=lambda x: x["strike"], reverse=True)
    return out


def fetch_yahoo_options(symbol: str, expiration: str | None = None) -> dict[str, Any]:
    """
    Public delayed chain. Works well for SPY/QQQ. SPX/SPXW is hit-or-miss on Yahoo.
    """
    url = f"https://query2.finance.yahoo.com/v7/finance/options/{urllib.parse.quote(symbol)}"
    data = http_json(url)
    result = (data.get("optionChain") or {}).get("result") or []
    if not result:
        raise RuntimeError(f"Yahoo returned no option chain for {symbol}")
    chain = result[0]
    quote = chain.get("quote") or {}
    expiries = chain.get("expirationDates") or []
    want = expiration
    if not want and expiries:
        first = datetime.fromtimestamp(int(expiries[0]), tz=timezone.utc).date().isoformat()
        want = first
    if want and expiries:
        want_ts = None
        for ts in expiries:
            d = datetime.fromtimestamp(int(ts), tz=timezone.utc).date().isoformat()
            if d == want:
                want_ts = int(ts)
                break
        if want_ts is None:
            want_ts = int(expiries[0])
            want = datetime.fromtimestamp(want_ts, tz=timezone.utc).date().isoformat()
        url2 = f"{url}?date={want_ts}"
        data = http_json(url2)
        result = (data.get("optionChain") or {}).get("result") or []
        chain = result[0]
        quote = chain.get("quote") or quote
    options = (chain.get("options") or [{}])[0]
    puts = _put_rows(options.get("puts") or [])
    if not puts:
        raise RuntimeError(f"Yahoo chain for {symbol} {want} has no put quotes")
    return {
        "source": "yahoo",
        "symbol": symbol,
        "spot": quote.get("regularMarketPrice") or quote.get("price"),
        "prior_close": quote.get("regularMarketPreviousClose") or quote.get("previousClose"),
        "expiration": want or today_iso(),
        "asof": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "puts": puts,
    }


def fetch_polygon_options(symbol: str, expiration: str | None = None, api_key: str | None = None) -> dict[str, Any]:
    key = (
        api_key
        or os.environ.get("POLYGON_API_KEY")
        or os.environ.get("POLYGON_KEY")
    )
    if not key:
        raise RuntimeError("Set POLYGON_API_KEY")
    exp = expiration or today_iso()
    q = urllib.parse.urlencode(
        {
            "contract_type": "put",
            "expiration_date": exp,
            "limit": 250,
            "sort": "strike_price",
            "order": "desc",
            "apiKey": key,
        }
    )
    url = f"https://api.polygon.io/v3/snapshot/options/{urllib.parse.quote(symbol)}?{q}"
    data = http_json(url)
    results = data.get("results") or []
    raw_puts = []
    for row in results:
        details = row.get("details") or {}
        greeks = row.get("greeks") or {}
        lq = row.get("last_quote") or {}
        raw_puts.append(
            {
                "strike": details.get("strike_price"),
                "bid": lq.get("bid"),
                "ask": lq.get("ask"),
                "delta": greeks.get("delta"),
            }
        )
    puts = _put_rows(raw_puts)
    if not puts:
        raise RuntimeError(f"Polygon returned no put quotes for {symbol} {exp}")
    und = (results[0].get("underlying_asset") or {}) if results else {}
    return {
        "source": "polygon",
        "symbol": symbol,
        "spot": und.get("price"),
        "expiration": exp,
        "asof": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "puts": puts,
    }


def fetch_tradier_options(symbol: str, expiration: str | None = None, token: str | None = None) -> dict[str, Any]:
    token = token or os.environ.get("TRADIER_TOKEN") or os.environ.get("TRADIER_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("Set TRADIER_TOKEN")
    base = os.environ.get("TRADIER_ENDPOINT", "https://api.tradier.com/v1").rstrip("/")
    exp = expiration or today_iso()
    url = (
        f"{base}/markets/options/chains?"
        + urllib.parse.urlencode({"symbol": symbol, "expiration": exp, "greeks": "true"})
    )
    data = http_json(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    options = ((data.get("options") or {}).get("option")) or []
    if isinstance(options, dict):
        options = [options]
    raw_puts = [o for o in options if str(o.get("option_type") or o.get("type") or "").lower() == "put"]
    puts = _put_rows(raw_puts)
    if not puts:
        raise RuntimeError(f"Tradier returned no put quotes for {symbol} {exp}")
    return {
        "source": "tradier",
        "symbol": symbol,
        "expiration": exp,
        "asof": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "puts": puts,
    }


BROKERS = {
    "yahoo": fetch_yahoo_options,
    "polygon": fetch_polygon_options,
    "tradier": fetch_tradier_options,
}


def fetch_chain(
    broker: str,
    symbol: str,
    expiration: str | None = None,
    creds: dict[str, Any] | None = None,
) -> dict[str, Any]:
    name = broker.lower().strip()
    if name not in BROKERS:
        raise RuntimeError(f"unknown broker {broker!r}. choose: {', '.join(BROKERS)}")
    creds = creds or {}
    if name == "polygon":
        return fetch_polygon_options(symbol, expiration, creds.get("polygon_api_key") or None)
    if name == "tradier":
        if creds.get("tradier_endpoint"):
            os.environ.setdefault("TRADIER_ENDPOINT", str(creds["tradier_endpoint"]))
        return fetch_tradier_options(symbol, expiration, creds.get("tradier_token") or None)
    return BROKERS[name](symbol, expiration)

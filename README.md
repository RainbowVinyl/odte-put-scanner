# 0DTE Improved Put Credit Spread Scanner

Mechanical scanner for an **SPX/SPXW 0DTE put credit spread**.

It is **not** the raw TastyLive ATM-every-day slide. That study is the baseline. This repo implements the patched book:

| Rule | Spec |
|---|---|
| Window | 09:00–09:05 America/Chicago |
| Short | ~20-delta put, else 0DTE expected-move put |
| Long | short − width |
| Width | $10 default, $20 max, $30 banned |
| Credit | **bid** (mid is reference only) |
| Winner | GTC cover at 75% of credit (keep 25%) |
| Loser | hold improved (20Δ/EM) to cash settle |
| ATM baseline | `--atm` — flatten 12:00 CT if 25% not hit |

Skip the session if any fire: scheduled macro (FOMC/CPI/NFP), overnight gap ≤ −0.6%, VIX1D > VIX, no chain, haircut credit < 15% of width, wide vertical quotes.

**Not financial advice.** Historical mid-price studies overstate live fills. A 0DTE put spread can lose nearly the full width.

## No-install (what to send other people)

Python is **not** required for recipients after you build once.

1. On GitHub: **Actions → Build no-install binaries → Run workflow**
2. Download `odte-scan-windows` (or macOS / Linux)
3. Send that folder. They double-click `odte-scan.exe`

See [BUILD.md](BUILD.md).

Until a workflow has run, this repo is source only — there is no checked-in `.exe`.

## Run from source

Needs Python 3.10+. No extra packages.

```bash
git clone https://github.com/RainbowVinyl/odte-put-scanner.git
cd odte-put-scanner
python3 scanner.py --chain chain.example.json
```

## Run

```bash
# sample chain
python3 scanner.py --chain chain.example.json

# your live dump + Yahoo spot/VIX overlay
python3 scanner.py --chain chain.json --live --width 10 --contracts 1

# original ATM baseline
python3 scanner.py --chain chain.json --atm

# JSON ticket
python3 scanner.py --chain chain.json --out ticket.json
```

Exit codes: `0` TRADE · `1` NO TRADE · `2` bad args/file.

## Chain file

Public Yahoo data does **not** give a reliable SPX 0DTE chain. Copy `chain.example.json` to `chain.json` and paste bids/asks from your broker.

```json
{
  "spot": 6688.57,
  "prior_close": 6716.09,
  "vix": 16.4,
  "vix1d": 15.1,
  "event": "",
  "expiration": "2026-09-17",
  "puts": [
    {"strike": 6660, "bid": 2.80, "ask": 3.10, "delta": -0.21}
  ]
}
```

Need puts at the short strike and at `short − width`. Put FOMC/CPI/NFP dates in `events.json` → `skip_dates`.

`--live` overlays Yahoo `^GSPC`, `^VIX`, `^VIX1D` onto the chain file. It does not replace the option quotes.

## Daily workflow

1. 09:00 CT — dump the 0DTE put chain into `chain.json`.
2. Run the scanner.
3. TRADE → work the printed GTC. NO TRADE → stand down.
4. Do not arm a second ticket until the first is closed ≥ 25%.

## Layout

```
scanner.py              CLI
config.json             width, friction, skip thresholds
events.json             skip dates
chain.example.json      failing-credit example
chain.pass.example.json richer-credit example
```

## Disclaimer

Educational scanner only. Does not place orders. Past TastyLive-style averages are one bull-market path, not a forecast.

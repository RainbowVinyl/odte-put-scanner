# Broker integration links

These are official pages. The scanner does not log in for you. Open a link, create *your* key, paste it into `integrations.json` on this computer.

| Source | What you get | Links |
|---|---|---|
| Yahoo | Delayed SPY/QQQ chain, no key | [SPY options](https://finance.yahoo.com/quote/SPY/options/) |
| Polygon | Paid options snapshot | [Sign up](https://polygon.io/dashboard/signup) · [API keys](https://polygon.io/dashboard/api-keys) · [Options docs](https://polygon.io/docs/options) |
| Tradier | Broker chain + greeks | [Sign up](https://www.tradier.com/) · [API token](https://dash.tradier.com/settings/api) · [Docs](https://documentation.tradier.com/brokerage-api) |
| tastytrade | Not wired yet; token later | [Site](https://tastytrade.com/) · [Developer](https://developer.tastytrade.com/) |
| IBKR | Not wired yet; TWS/Gateway later | [Site](https://www.interactivebrokers.com/) · [TWS API](https://www.interactivebrokers.com/en/trading/ib-api.php) |
| Cboe | Manual delayed SPX table | [SPX](https://www.cboe.com/delayed_quotes/spx/quote_table) · [SPXW](https://www.cboe.com/delayed_quotes/spxw/quote_table) |

```bash
python3 scanner.py --links
python3 scanner.py --setup
```

`--setup` can open Polygon + Tradier signup/token pages in your default browser.

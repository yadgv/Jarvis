"""Share and crypto prices from Yahoo Finance's public chart endpoint (no key)."""
import requests

URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def stock_price(a):
    symbol = (a.get("symbol") or "").strip().upper()
    if not symbol:
        return "No ticker symbol given."
    r = requests.get(URL.format(symbol=symbol), params={"range": "1d", "interval": "1d"},
                     headers=HEADERS, timeout=10)
    if r.status_code == 404:
        return f"No quote found for {symbol}. Check the ticker symbol."
    r.raise_for_status()
    result = (r.json().get("chart", {}).get("result") or [None])[0]
    if not result:
        return f"No quote found for {symbol}."
    m = result["meta"]
    price = m.get("regularMarketPrice")
    prev = m.get("chartPreviousClose") or m.get("previousClose")
    name = m.get("longName") or m.get("shortName") or symbol
    text = f"{name} ({symbol}): {price:,.2f} {m.get('currency', '')}"
    if price is not None and prev:
        change = (price - prev) / prev * 100
        text += f", {'up' if change >= 0 else 'down'} {abs(change):.1f}% from the previous close"
    if m.get("exchangeName"):
        text += f" on {m['exchangeName']}"
    return text + "."


SKILLS = [
    {
        "name": "stock_price",
        "description": (
            "Latest price of a stock, ETF, index or crypto by its Yahoo Finance ticker, "
            "e.g. NVDA, AAPL, SHOP.TO (Toronto), ^GSPC (S&P 500), BTC-USD."
        ),
        "parameters": {
            "type": "object",
            "properties": {"symbol": {"type": "string", "description": "Ticker symbol"}},
            "required": ["symbol"],
        },
        "run": stock_price,
    },
]

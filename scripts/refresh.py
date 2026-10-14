#!/usr/bin/env python3
"""Fail-closed, provenance-first market snapshot collector. Standard library only.

Never substitute a refresh timestamp for the observation timestamp. Prices from
single public sources are labeled 'single_source', never independently verified.
"""
import csv
import io
import json
import math
import os
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree

UTC = timezone.utc
OUTPUT = Path("data/latest.json")
HEADERS = {"User-Agent": "MarketPipeline/2.0 (+https://github.com/yuvaltevelov/market-pipeline)", "Accept": "application/json,text/csv,application/xml,*/*"}
SPECS = [
    ("PLTR", "PLTR · Palantir", "מניה · סגירה יומית", "USD", "share"),
    ("XAUUSD", "זהב XAU/USD", "ספוט אינדיקטיבי · אונקיית טרוי", "USD", "troy_oz"),
    ("BTC", "Bitcoin", "קריפטו · USD", "USD", "coin"),
    ("ETH", "Ethereum", "קריפטו · USD", "USD", "coin"),
    ("BRENT", "ברנט · מחיר ספוט יומי", "נפט · חבית", "USD", "barrel"),
    ("VIX", "VIX · סגירה יומית", "מדד תנודתיות", "index", "index"),
]
SOURCES = {
    "PLTR": ("Stooq", "https://stooq.com/q/?s=pltr.us", "daily_close"),
    "XAUUSD": ("Gold-API", "https://gold-api.com/docs", "indicative_spot"),
    "BTC": ("CoinGecko", "https://www.coingecko.com/en/coins/bitcoin", "indicative_spot"),
    "ETH": ("CoinGecko", "https://www.coingecko.com/en/coins/ethereum", "indicative_spot"),
    "BRENT": ("FRED / EIA", "https://fred.stlouisfed.org/series/DCOILBRENTEU", "daily_spot"),
    "VIX": ("FRED / CBOE", "https://fred.stlouisfed.org/series/VIXCLS", "daily_close"),
}

def utcnow():
    return datetime.now(UTC)

def iso(dt):
    return dt.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

def request_bytes(url):
    req = Request(url, headers=HEADERS)
    with urlopen(req, timeout=16) as response:
        data = response.read(2_000_001)
        if len(data) > 2_000_000:
            raise ValueError("oversized source response")
        return data

def fetch_json(url):
    return json.loads(request_bytes(url).decode("utf-8"))

def numeric(value):
    n = float(value)
    if not math.isfinite(n) or n <= 0 or n > 10_000_000:
        raise ValueError("invalid quote")
    return n

def date_rows_csv(raw, value_column):
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    values = []
    for row in rows:
        d = row.get("DATE") or row.get("Date") or row.get("observation_date")
        p = row.get(value_column)
        if not d or not p or p == ".":
            continue
        try:
            date = datetime.strptime(d, "%Y-%m-%d").date()
            price = numeric(p)
            values.append((date, price))
        except (ValueError, TypeError):
            continue
    if not values:
        raise ValueError("no usable dated quotes")
    values.sort(key=lambda x: x[0])
    return values[-2:]

def pct_from_pair(rows):
    if len(rows) < 2:
        return None
    previous = rows[-2][1]
    return round((rows[-1][1] / previous - 1) * 100, 3)

def make_quote(asset_id, price, observed, now, change=None):
    # Observed can be a calendar DATE for closing data or a timezone-aware
    # datetime for spot feeds. Do not invent intraday timestamps for EOD data.
    if isinstance(observed, datetime):
        if observed.tzinfo is None:
            raise ValueError("observation lacks timezone")
        age = (now - observed.astimezone(UTC)).total_seconds()
        if age < -300:
            raise ValueError("future observation")
        ttl = 3600 if asset_id == "XAUUSD" else 10800
        stale = age > ttl
        as_of = iso(observed)
        granularity = "timestamp"
    else:
        age = (now.date() - observed).days
        if age < 0:
            raise ValueError("future trading date")
        stale = age > (5 if asset_id == "PLTR" else 7)
        as_of = observed.isoformat()
        granularity = "date"
    source, url, basis = SOURCES[asset_id]
    if change is not None and (not math.isfinite(float(change)) or abs(float(change)) > 100):
        change = None
    return {
        "price": round(numeric(price), 4),
        "change_percent": round(float(change), 3) if change is not None else None,
        "as_of": as_of, "granularity": granularity,
        "source": source, "source_url": url, "pricing_basis": basis,
        "quality": "stale" if stale else "reported",
        "verification": "single_source",
        "warning": "המקור אינו אימות עצמאי נוסף" if not stale else "נתון ישן — אינו מחיר עדכני",
    }

def collect_stooq(now):
    start = (now - timedelta(days=15)).strftime("%Y%m%d")
    end = now.strftime("%Y%m%d")
    url = "https://stooq.com/q/d/l/?" + urlencode({"s": "pltr.us", "i": "d", "d1": start, "d2": end})
    try:
        rows = date_rows_csv(request_bytes(url), "Close")
        return make_quote("PLTR", rows[-1][1], rows[-1][0], now, pct_from_pair(rows))
    except Exception:
        # Some Stooq IPs receive quota/no-data responses on historical CSV.
        # The quote endpoint is still the SAME source, not independent verification.
        # A quote may be intraday, so it must never be labeled 'daily close'.
        fallback = "https://stooq.com/q/l/?" + urlencode(
            {"s": "pltr.us", "f": "sd2t2ohlcvnp", "h": "", "e": "csv"}
        )
        raw = request_bytes(fallback).decode("utf-8-sig")
        rows = list(csv.DictReader(io.StringIO(raw)))
        if len(rows) != 1 or rows[0].get("Symbol", "").lower() != "pltr.us":
            raise ValueError("Stooq quote identity mismatch or no data")
        row = rows[0]
        date = datetime.strptime(row["Date"], "%Y-%m-%d").date()
        price = numeric(row["Close"])
        change = None
        try:
            previous = numeric(row["Prev"])
            change = round((price / previous - 1) * 100, 3)
        except (KeyError, TypeError, ValueError):
            pass
        quote = make_quote("PLTR", price, date, now, change)
        quote["pricing_basis"] = "delayed_market_quote"
        quote["warning"] = "ציטוט אחרון מהספק; עשוי להיות מעוכב או תוך-יומי"
        return quote

def collect_gold(now):
    data = fetch_json("https://api.gold-api.com/price/XAU")
    observed = datetime.fromisoformat(data["updatedAt"].replace("Z", "+00:00"))
    return make_quote("XAUUSD", data["price"], observed, now)

def collect_crypto(now):
    params = urlencode({
        "ids": "bitcoin,ethereum", "vs_currencies": "usd",
        "include_24hr_change": "true", "include_last_updated_at": "true"
    })
    data = fetch_json("https://api.coingecko.com/api/v3/simple/price?" + params)
    result = {}
    for asset_id, key in [("BTC", "bitcoin"), ("ETH", "ethereum")]:
        try:
            item = data[key]
            observed = datetime.fromtimestamp(int(item["last_updated_at"]), UTC)
            result[asset_id] = make_quote(asset_id, item["usd"], observed, now, item.get("usd_24h_change"))
        except (KeyError, TypeError, ValueError, OverflowError):
            result[asset_id] = None
    return result

def collect_fred(asset_id, series, now):
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?" + urlencode({
        "id": series, "cosd": (now - timedelta(days=20)).date().isoformat()
    })
    rows = date_rows_csv(request_bytes(url), series)
    return make_quote(asset_id, rows[-1][1], rows[-1][0], now, pct_from_pair(rows))

def collect_fed_releases(now):
    """Titles are official published titles, not AI-created causal assertions."""
    try:
        root = ElementTree.fromstring(request_bytes("https://www.federalreserve.gov/feeds/press_all.xml"))
        news = []
        for item in root.findall(".//item")[:20]:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            published = (item.findtext("pubDate") or "").strip()
            if not title or not link.startswith("https://www.federalreserve.gov/") or not published:
                continue
            at = parsedate_to_datetime(published)
            if at.tzinfo is None or not (0 <= (now - at.astimezone(UTC)).total_seconds() <= 7 * 86400):
                continue
            news.append({"title": title[:240], "url": link, "published_at": iso(at), "source": "Federal Reserve"})
        return news[:5]
    except Exception:
        return []

def blank(asset_id, error="source_unavailable"):
    source, url, basis = SOURCES[asset_id]
    return {"price": None, "change_percent": None, "as_of": None,
            "granularity": None, "source": source, "source_url": url,
            "pricing_basis": basis, "quality": "unavailable",
            "verification": "none", "warning": error}

def build_snapshot(now=None, collectors=None):
    now = now or utcnow()
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    collectors = collectors or {
        "PLTR": lambda: collect_stooq(now),
        "XAUUSD": lambda: collect_gold(now),
        "CRYPTO": lambda: collect_crypto(now),
        "BRENT": lambda: collect_fred("BRENT", "DCOILBRENTEU", now),
        "VIX": lambda: collect_fred("VIX", "VIXCLS", now),
        "NEWS": lambda: collect_fed_releases(now),
    }
    observations = {}
    warnings = []
    for key in ("PLTR", "XAUUSD", "CRYPTO", "BRENT", "VIX"):
        try:
            value = collectors[key]()
            if key == "CRYPTO":
                observations.update(value)
            else:
                observations[key] = value
        except Exception as exc:
            warnings.append(key + ": " + type(exc).__name__)
    assets = []
    for asset_id, name, description, currency, unit in SPECS:
        quote = observations.get(asset_id) or blank(asset_id)
        assets.append({"id": asset_id, "name": name, "description": description,
                       "currency": currency, "unit": unit, **quote})
    valid = sum(a["quality"] == "reported" for a in assets)
    stale = sum(a["quality"] == "stale" for a in assets)
    if valid == 0:
        raise RuntimeError("no current source observations: refusing to publish")
    try:
        news = collectors["NEWS"]()
    except Exception:
        news = []
    signals = [
        {"title": "אימות מקורות", "text": str(valid) + " מתוך " + str(len(assets)) +
         " מקורות דיווחו נתון תקף לזמנם; אין אימות בלתי תלוי בין ספקים."},
        {"title": "זמן מדידה", "text": "לכל נכס מוצג זמן המדידה של המקור, בנפרד מזמן יצירת הדוח."},
        {"title": "ניתוח זהיר", "text": "שינוי יומי אינו מעיד לבדו על סיבת התנועה או על תנועה עתידית."},
    ]
    if stale:
        signals.append({"title": "מידע ישן", "text": str(stale) + " נכסים סומנו כישנים ולא יוצגו כמחיר נוכחי."})
    return {"schema_version": 2, "generated_at": iso(now),
            "status": "complete" if valid == len(assets) else "partial",
            "quality": {"reported": valid, "stale": stale, "unavailable": len(assets)-valid-stale,
                        "cross_verified": 0, "source_errors": warnings},
            "assets": assets, "signals": signals, "news": news,
            "disclaimer": "נתוני מקור חינמי, חלקם מעוכבים או אינדיקטיביים. ללא אימות צולב וללא המלצת השקעה."}

def main():
    snapshot = build_snapshot()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temp = OUTPUT.with_suffix(".json.tmp")
    temp.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, OUTPUT)
    print("Published:", snapshot["status"], snapshot["quality"])

if __name__ == "__main__":
    main()

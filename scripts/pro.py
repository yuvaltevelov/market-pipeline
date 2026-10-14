"""Free-source historical OHLCV research snapshot.

Coin/stock market datasets are never conflated with spot gold or Brent.
Unofficial Yahoo chart endpoints can be restricted or throttled; fail closed.
"""
from __future__ import annotations
import json
import os
import time
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import quote,urlencode
from urllib.request import Request,urlopen
from .engine import analyze,clean_bars

UTC=timezone.utc
OUTPUT=Path("data/pro.json")
MAX_BYTES=3_000_000
HEADERS={"User-Agent":"MarketPipelinePro/1.0 (research; github.com/yuvaltevelov/market-pipeline)","Accept":"application/json"}
WATCHLIST=[
 ("PLTR","Palantir","stock","PLTR"),
 ("NVDA","NVIDIA","stock","NVDA"),
 ("AMD","AMD","stock","AMD"),
 ("MSFT","Microsoft","stock","MSFT"),
 ("TSM","TSMC ADR","stock","TSM"),
 ("SPY","SPDR S&P 500 ETF","etf","SPY"),
 ("QQQ","Invesco Nasdaq 100 ETF","etf","QQQ"),
 ("SMH","VanEck Semiconductor ETF","etf","SMH"),
 ("IWM","iShares Russell 2000 ETF","etf","IWM"),
 ("GLD","SPDR Gold Shares · זהב ETF","etf","GLD"),
 ("USO","United States Oil Fund · נפט ETF","etf","USO"),
 ("EURUSD","EUR/USD · spot indicative","fx","EURUSD=X"),
 ("GBPUSD","GBP/USD · spot indicative","fx","GBPUSD=X"),
 ("USDJPY","USD/JPY · spot indicative","fx","JPY=X"),
 ("GC_F","חוזה עתידי זהב · GC","futures","GC=F"),
 ("BZ_F","חוזה עתידי Brent · BZ","futures","BZ=F"),
 ("BTC","Bitcoin · Kraken XBT/USD","crypto","XBTUSD"),
 ("ETH","Ethereum · Kraken ETH/USD","crypto","ETHUSD"),
]
INTRADAY={"PLTR","SPY","QQQ","EURUSD","BTC","ETH"}
def fetch_json(url):
    req=Request(url,headers=HEADERS)
    with urlopen(req,timeout=15) as response:
        raw=response.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES:raise ValueError("provider response too large")
        return json.loads(raw.decode("utf-8"))

def parse_yahoo(payload,now,interval):
    charts=payload["chart"]
    if charts.get("error"):raise ValueError("provider chart error")
    item=charts["result"][0]
    times=item.get("timestamp") or []
    q=item["indicators"]["quote"][0]
    count=min(len(times),*(len(q.get(k,[])) for k in ("open","high","low","close","volume")))
    seconds=3600 if interval=="60m" else 86400
    out=[]
    for i in range(count):
        t=times[i]
        # Last (incomplete) candle must never create signals or backtest entries.
        if not isinstance(t,int) or t+seconds>now.timestamp():
            continue
        try:
            v=q["volume"][i]
            b={"time":t,"open":q["open"][i],"high":q["high"][i],
               "low":q["low"][i],"close":q["close"][i],"volume":v if v is not None and v>0 else None}
            out.append(b)
        except (TypeError,ValueError,IndexError):continue
    return clean_bars(out)

def yahoo(symbol,interval,now):
    encoded=quote(symbol,safe="")
    query=urlencode({"range":"1y" if interval=="1d" else "60d",
                     "interval":interval,"includePrePost":"false",
                     "events":"false"})
    payload=fetch_json("https://query1.finance.yahoo.com/v8/finance/chart/"+encoded+"?"+query)
    return parse_yahoo(payload,now,interval)

def parse_kraken(payload,now,interval):
    if payload.get("error"):raise ValueError("Kraken error response")
    results=payload["result"]
    key=next(k for k in results if k!="last")
    output=[]
    seconds=interval*60
    for row in results[key]:
        try:
            t=int(row[0])
            if t+seconds>now.timestamp():continue
            output.append({"time":t,"open":row[1],"high":row[2],
                           "low":row[3],"close":row[4],"volume":row[6]})
        except (ValueError,IndexError,TypeError):continue
    return clean_bars(output)

def kraken(pair,interval,now):
    url="https://api.kraken.com/0/public/OHLC?"+urlencode({"pair":pair,"interval":1440 if interval=="1d" else 60})
    return parse_kraken(fetch_json(url),now,1440 if interval=="1d" else 60)

def collect_one(id_,name,category,symbol,timeframe,now,load_yahoo=yahoo,load_kraken=kraken):
    source="Kraken" if category=="crypto" else "Yahoo Finance chart (unofficial)"
    source_url=("https://docs.kraken.com/api/docs/rest-api/get-ohlc-data"
                if category=="crypto" else "https://finance.yahoo.com/quote/"+quote(symbol,safe="")+"/history/")
    record={"id":id_,"name":name,"category":category,"symbol":symbol,
            "timeframe":timeframe,"source":source,"source_url":source_url,
            "market_data_verification":"single_source","pricing_basis":
            "Kraken exchange OHLCV" if category=="crypto" else "unofficial chart feed",
            "status":"unavailable","error":None}
    try:
        bars=(load_kraken(symbol,timeframe,now) if category=="crypto"
              else load_yahoo(symbol,timeframe,now))
        max_age=3*86400 if timeframe=="1d" else 4*3600
        if category=="crypto":max_age=2*86400 if timeframe=="1d" else 2*3600
        if len(bars)<65:raise ValueError("insufficient completed candles")
        if now.timestamp()-bars[-1]["time"] > max_age:
            raise ValueError("stale completed candles")
        analysis=analyze(bars,timeframe)
        record.update(analysis)
        record["status"]="reported"
        record["currency"]="USD" if category!="fx" else "quote currency"
        record["price"]=bars[-1]["close"]
        record["volume_source"]="exchange volume" if category=="crypto" else ("reported instrument volume" if analysis["indicators"].get("volume_available") else "unavailable")
    except Exception as exc:
        # Do not expose any unvalidated quote or incomplete chart on failure.
        record["error"]=type(exc).__name__
        record["score"]=None
        record["bias"]="unavailable"
        record["price"]=None
        record["as_of"]=None
        record["indicators"]={}
        record["backtest"]={"status":"not_run"}
        record["chart"]=[]
        record["reasons"]=["לא התקבלו מספיק נתונים אמינים מהספק"]
        record["flags"]=[]
        record["data_needs"]={"aggressor_side_trades":"unavailable",
                              "level2_order_book":"unavailable",
                              "options_flow":"unavailable",
                              "institutional_identity":"unavailable"}
    return record

def build_snapshot(now=None,collector=collect_one,watchlist=None):
    now=now or datetime.now(UTC)
    if now.tzinfo is None:raise ValueError("naive timestamp")
    watchlist=WATCHLIST if watchlist is None else watchlist
    assets=[]
    for id_,name,category,symbol in watchlist:
        for timeframe in (("1d","60m") if id_ in INTRADAY else ("1d",)):
            assets.append(collector(id_,name,category,symbol,timeframe,now))
            # Slow free Yahoo data access; improve rate limit behavior without evasion.
            if collector is collect_one and os.getenv("PRO_DELAY_SECONDS","0")!="0":
                time.sleep(float(os.environ["PRO_DELAY_SECONDS"]))
    good=sum(x["status"]=="reported" for x in assets)
    counts={"valid":good,"unavailable":len(assets)-good,"cross_verified":0,"total":len(assets)}
    return {
      "schema_version":3,
      "generated_at":now.isoformat(timespec="seconds").replace("+00:00","Z"),
      "status":"partial" if good<len(assets) else "complete",
      "coverage":counts,
      "assets":assets,
      "scope":{"ohlcv":"historical research only","timeframes":["1d","60m"],
               "orderflow":"not available","institutional_positions":"not observable",
               "confidence":"heuristic score; NOT probability",
               "backtest":"chronological holdout, next open, disclosed fixed rule"},
      "disclaimer":"מחקר היסטורי בלבד; ספקים חינמיים עשויים להתעכב או להיחסם. אין ייעוץ השקעות, המלצת מסחר, זיהוי מוכח של מוסדיים או נתוני פקודות."
    }

def publish():
    snapshot=build_snapshot()
    # Do not destroy a previously valid data snapshot on total source outage.
    if snapshot["coverage"]["valid"]==0:
        raise RuntimeError("All providers unavailable; abort publication")
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    tmp=OUTPUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(snapshot,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    os.replace(tmp,OUTPUT)
    print("Market Pipeline Pro:",snapshot["coverage"])

if __name__=="__main__":
    publish()

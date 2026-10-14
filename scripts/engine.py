"""Deterministic, auditable OHLCV research engine (not an order-flow feed).

Input contains completed market bars ONLY. Analysis uses closed bars; historical
decisions use past-only features, execute at NEXT bar open, pay transaction costs.
Money flow measures (CMF/MFI/OBV) are OHLCV proxies, NOT institutional orders.
"""
from __future__ import annotations
import math
from statistics import mean

MIN_BARS = 65

def finite(v):
    return isinstance(v, (float, int)) and not isinstance(v, bool) and math.isfinite(v)

def clean_bars(rows):
    out = []
    last = -1
    for b in rows:
        try:
            t = int(b["time"])
            o,h,l,c = (float(b[k]) for k in ("open","high","low","close"))
            raw_v = b.get("volume")
            v = None if raw_v is None else float(raw_v)
            if not (0 < l <= min(o,c) <= max(o,c) <= h and all(map(finite,(o,h,l,c)))):
                continue
            if v is not None and (not finite(v) or v < 0):
                continue
            if t <= last:
                continue
            out.append(dict(time=t,open=o,high=h,low=l,close=c,volume=v))
            last = t
        except (ValueError,TypeError,KeyError,OverflowError):
            continue
    return out

def ema(values, period):
    if len(values) < period:
        return None
    value = mean(values[:period])
    k = 2/(period+1)
    for x in values[period:]:
        value = x*k + value*(1-k)
    return value

def rsi(closes, period=14):
    if len(closes) <= period:
        return None
    differences = [b-a for a,b in zip(closes[:-1],closes[1:])]
    gain = mean(max(x,0) for x in differences[:period])
    loss = mean(max(-x,0) for x in differences[:period])
    for change in differences[period:]:
        gain = (gain*(period-1)+max(change,0))/period
        loss = (loss*(period-1)+max(-change,0))/period
    if loss == 0:
        return 100.0 if gain > 0 else 50.0
    return 100-100/(1+gain/loss)

def atr(bars, period=14):
    if len(bars) < period+1:
        return None
    trs = []
    for i in range(1,len(bars)):
        b=bars[i]; previous=bars[i-1]["close"]
        trs.append(max(b["high"]-b["low"],abs(b["high"]-previous),abs(b["low"]-previous)))
    average=mean(trs[:period])
    for tr in trs[period:]:
        average=(average*(period-1)+tr)/period
    return average

def volume_metrics(bars):
    # Volume-based metrics only when 21+ bars contain genuine positive quantities.
    if len(bars)<26 or any(b["volume"] is None or b["volume"]<=0 for b in bars[-26:]):
        return {"rvol":None,"cmf20":None,"mfi14":None,"obv_direction":None,
                "rolling_vwap20":None,"volume_available":False}
    prev = [b["volume"] for b in bars[-21:-1]]
    rvol = bars[-1]["volume"]/mean(prev) if mean(prev)>0 else None
    window=bars[-20:]
    dollarflow=[]
    vw_sum=0
    for b in window:
        rng=b["high"]-b["low"]
        multiplier=((b["close"]-b["low"])-(b["high"]-b["close"]))/rng if rng>0 else 0
        dollarflow.append(multiplier*b["volume"])
        vw_sum+=((b["high"]+b["low"]+b["close"])/3)*b["volume"]
    total=sum(b["volume"] for b in window)
    cmf=sum(dollarflow)/total if total else None
    vwap=vw_sum/total if total else None
    series=bars[-16:]
    positive=negative=0.0
    for a,b in zip(series[:-1],series[1:]):
        av=(a["high"]+a["low"]+a["close"])/3
        bv=(b["high"]+b["low"]+b["close"])/3
        money=bv*b["volume"]
        if bv>av:positive+=money
        elif bv<av:negative+=money
    mfi=100 if negative==0 and positive>0 else 50 if negative==0 else 100-100/(1+positive/negative)
    # Net on-balance volume change over prior five bars (not signed trade volume).
    change=0.0
    for a,b in zip(bars[-6:-1],bars[-5:]):
        change+=b["volume"]*(1 if b["close"]>a["close"] else -1 if b["close"]<a["close"] else 0)
    return {"rvol":rvol,"cmf20":cmf,"mfi14":mfi,
            "obv_direction":1 if change>0 else -1 if change<0 else 0,
            "rolling_vwap20":vwap,"volume_available":True}

def market_structure(bars):
    if len(bars)<24:
        return {"sweep":"none","breakout":"none","fvg":"none"}
    b=bars[-1]; high=max(x["high"] for x in bars[-21:-1])
    low=min(x["low"] for x in bars[-21:-1])
    sweep=("bullish" if b["low"]<low and b["close"]>low
           else "bearish" if b["high"]>high and b["close"]<high else "none")
    breakout="bullish" if b["close"]>high else "bearish" if b["close"]<low else "none"
    old=bars[-3]
    fvg="bullish" if b["low"]>old["high"] else "bearish" if b["high"]<old["low"] else "none"
    return {"sweep":sweep,"breakout":breakout,"fvg":fvg}

def indicators(bars):
    if len(bars)<MIN_BARS:
        return None
    c=[b["close"] for b in bars]
    close=c[-1]
    f={
      "close":close,
      "ema20":ema(c,20),"ema50":ema(c,50),"sma200":mean(c[-200:]) if len(c)>=200 else None,
      "rsi14":rsi(c),"atr14":atr(bars),
      "momentum20_pct":100*(close/c[-21]-1),
      "change_pct":100*(close/c[-2]-1),
      **volume_metrics(bars),**market_structure(bars)
    }
    return f

def interpretation(f):
    """A rule-based research score 0..100, NOT a forecast probability."""
    if f is None:
        return {"score":None,"bias":"insufficient","reasons":["אין מספיק נרות שהושלמו"],"flags":[]}
    score=50
    reasons=[];flags=[]
    trend=1 if f["ema20"]>f["ema50"] else -1
    score+=16*trend
    reasons.append("ממוצע 20 מעל 50" if trend>0 else "ממוצע 20 מתחת 50")
    if f["sma200"] is not None:
        score+=8 if f["close"]>f["sma200"] else -8
        reasons.append("מחיר מעל ממוצע 200" if f["close"]>f["sma200"] else "מחיר מתחת ממוצע 200")
    move=1 if f["momentum20_pct"]>2 else -1 if f["momentum20_pct"]< -2 else 0
    score+=8*move
    if move:reasons.append("מומנטום 20 נרות חיובי" if move>0 else "מומנטום 20 נרות שלילי")
    score+=5 if 50<=f["rsi14"]<=70 else -5 if f["rsi14"]<40 or f["rsi14"]>80 else 0
    if f["volume_available"]:
        flow=1 if f["cmf20"]>0.08 else -1 if f["cmf20"]< -0.08 else 0
        score+=8*flow
        if flow:reasons.append("CMF חיובי (פרוקסי ללחץ קנייה)" if flow>0 else "CMF שלילי (פרוקסי ללחץ מכירה)")
        if f["rvol"]>=1.8:
            flags.append("נפח חריג פי %.2f מהממוצע" % f["rvol"])
            score+=6 if f["change_pct"]>0 else -6 if f["change_pct"]<0 else 0
        if f["mfi14"]>=80:flags.append("MFI גבוה; סיכון למיצוי")
        if f["mfi14"]<=20:flags.append("MFI נמוך; אין בכך הבטחת היפוך")
    else:
        flags.append("אין נפח מסחר אמין: RVOL/CMF/MFI/OBV לא מחושבים")
    for k,text in (("sweep","נזילות"),("breakout","פריצה"),("fvg","פער שווי הוגן")):
        s=f[k]
        if s!="none":
            score+=5 if s=="bullish" else -5
            flags.append(text+" "+("שורי" if s=="bullish" else "דובי")+" — תבנית בלבד, לא ראיה למניפולציה")
    score=max(0,min(100,score))
    bias="bullish" if score>=65 else "bearish" if score<=35 else "neutral"
    return {"score":score,"bias":bias,"reasons":reasons,"flags":flags}

def backtest(bars,horizon=5,cost_bps=20):
    """Fixed long-only heuristic, non-overlapping OOS trades.

    Signal at close of i; enter at i+1 OPEN; exit at i+1+h OPEN.
    Indicator rule is not trained/fitted; last quarter is chronological holdout.
    Returns unavailable rather than unreliable probabilities from tiny samples.
    """
    if len(bars)<180:
        return {"status":"insufficient_history","trades":0,
                "method":"Fixed rule, last 25% chronological holdout, next-open execution"}
    cut=max(100,int(len(bars)*.75))
    trades=[]
    equity=1.0;peak=1.0;dd=0.0
    i=cut
    while i+1+horizon < len(bars):
        f=indicators(bars[:i+1])
        signal=interpretation(f)
        if signal["bias"]=="bullish" and f["rsi14"]<75:
            start=bars[i+1]["open"];end=bars[i+1+horizon]["open"]
            ret=end/start-1-cost_bps/10000
            trades.append(ret)
            equity*=1+ret
            peak=max(peak,equity)
            dd=min(dd,equity/peak-1)
            i+=horizon+1
        else:
            i+=1
    if len(trades)<5:
        return {"status":"insufficient_trades","trades":len(trades),
                "method":"Long-only fixed rule; chronological 25% holdout"}
    benchmark=bars[-1]["close"]/bars[cut+1]["open"]-1-cost_bps/10000
    return {"status":"measured","trades":len(trades),
            "win_rate_pct":round(100*sum(r>0 for r in trades)/len(trades),1),
            "total_return_pct":round((equity-1)*100,2),
            "max_drawdown_pct":round(dd*100,2),
            "buy_hold_same_window_pct":round(benchmark*100,2),
            "cost_bps_round_trip":cost_bps,
            "method":"Fixed long-only heuristic, 25% chronological holdout; next-bar OPEN, exit after "+str(horizon)+" bars; no position sizing/borrow costs. NOT a forecast probability."}

def analyze(bars,timeframe="1d",backtest_enabled=True):
    valid=clean_bars(bars)
    f=indicators(valid)
    signal=interpretation(f)
    bt=backtest(valid,horizon=5 if timeframe=="1d" else 8) if backtest_enabled else {"status":"not_run"}
    output={"bars":len(valid),"timeframe":timeframe,
            "as_of":valid[-1]["time"] if valid else None,
            **signal,"backtest":bt,
            "data_needs":{"aggressor_side_trades":"unavailable","level2_order_book":"unavailable",
                          "options_flow":"unavailable","institutional_identity":"unavailable"}}
    if f is not None:
        rounded={}
        for k,v in f.items():
            if isinstance(v,float):rounded[k]=round(v,4)
            else:rounded[k]=v
        output["indicators"]=rounded
    else:output["indicators"]={}
    # Historical close-only series for a small visual; never add fabricated OHLCV.
    output["chart"]=[{"time":x["time"],"close":round(x["close"],5)} for x in valid[-80:]]
    return output

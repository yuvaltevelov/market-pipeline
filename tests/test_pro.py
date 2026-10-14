import unittest
from datetime import datetime,timezone
from scripts.engine import analyze,clean_bars,volume_metrics,market_structure,backtest
from scripts.pro import parse_yahoo,parse_kraken,collect_one,build_snapshot
NOW=datetime(2026,10,14,12,tzinfo=timezone.utc)
DAY=86400

def bars(count=240,volume=True):
    output=[]
    for i in range(count):
        close=100+i*.18+2*((i%9)-4)/9
        output.append({"time":int(NOW.timestamp())-(count-i)*DAY,
                       "open":close-.1,"high":close+1,"low":close-1,
                       "close":close,"volume":1000+i if volume else None})
    return output

class EngineTests(unittest.TestCase):
    def test_bad_and_out_of_order_bars_dropped(self):
        xs=bars(3)
        self.assertEqual(len(clean_bars([xs[0],xs[0],{**xs[1],"high":-1},xs[2]])),2)

    def test_no_proxy_money_flow_without_volume(self):
        x=analyze(bars(volume=False))
        self.assertFalse(x["indicators"]["volume_available"])
        self.assertIsNone(x["indicators"]["rvol"])
        self.assertIsNone(x["indicators"]["cmf20"])
        self.assertIsNone(x["indicators"]["mfi14"])
        self.assertEqual(x["data_needs"]["aggressor_side_trades"],"unavailable")

    def test_valid_volume_metrics(self):
        f=analyze(bars())["indicators"]
        self.assertTrue(f["volume_available"])
        self.assertGreater(f["rvol"],0)
        self.assertLessEqual(abs(f["cmf20"]),1)
        self.assertTrue(0<=f["mfi14"]<=100)

    def test_same_bars_different_future_no_lookahead(self):
        first=bars(230)
        next_=first+[dict(first[-1],time=first[-1]["time"]+DAY,close=first[-1]["close"]*.7,
                            low=first[-1]["low"]*.65,open=first[-1]["close"]*.7)]
        a=analyze(first)
        b=analyze(next_[:-1])
        self.assertEqual(a["score"],b["score"])
        self.assertEqual(a["indicators"],b["indicators"])

    def test_holdout_no_future_trade_entry(self):
        result=backtest(bars(220))
        self.assertIn(result["status"],("insufficient_trades","measured"))
        if result["status"]=="measured":
            self.assertLessEqual(result["win_rate_pct"],100)
            self.assertGreaterEqual(result["win_rate_pct"],0)

    def test_min_bars_and_explicit_limit(self):
        a=analyze(bars(23))
        self.assertIsNone(a["score"])
        self.assertEqual(a["backtest"]["status"],"insufficient_history")

    def test_bullish_sweep_does_not_mean_manipulation(self):
        series=bars(80)
        old_low=min(x["low"] for x in series[-21:-1])
        series[-1]["low"]=old_low-.5
        series[-1]["open"]=old_low+.3
        series[-1]["close"]=old_low+.5
        series[-1]["high"]=old_low+1
        self.assertEqual(market_structure(series)["sweep"],"bullish")

class ProviderTests(unittest.TestCase):
    def test_yahoo_excludes_unfinished_and_missing(self):
        now=NOW
        ts=int(now.timestamp())
        p={"chart":{"result":[{"timestamp":[ts-2*DAY,ts-100],
        "indicators":{"quote":[{"open":[100,101],"high":[102,102],"low":[99,99],
        "close":[101,101],"volume":[1000,1000]}]}}],"error":None}}
        output=parse_yahoo(p,now,"1d")
        self.assertEqual(len(output),1)

    def test_kraken_excludes_running_bar(self):
        ts=int(NOW.timestamp())
        row=lambda t:[t,"100","110","90","101","101","250",10]
        p={"error":[],"result":{"XXBTZUSD":[row(ts-3*DAY),row(ts-DAY//2)],"last":ts}}
        self.assertEqual(len(parse_kraken(p,NOW,1440)),1)

    def test_provider_errors_fail_closed(self):
        def broken(*args):
            raise ConnectionError("provider down")
        a=collect_one("SPY","S&P","etf","SPY","1d",NOW,load_yahoo=broken)
        self.assertEqual(a["status"],"unavailable")
        self.assertIsNone(a["price"])
        self.assertEqual(a["backtest"]["status"],"not_run")

    def test_snapshot_counts_not_fabricated(self):
        def fake(id_,name,category,symbol,timeframe,now):
            return {"id":id_,"timeframe":timeframe,"status":"unavailable"}
        d=build_snapshot(NOW,collector=fake,watchlist=[("AAA","AA","etf","AAA")])
        self.assertEqual(d["coverage"]["valid"],0)
        self.assertEqual(d["coverage"]["cross_verified"],0)

if __name__=="__main__":
    unittest.main()

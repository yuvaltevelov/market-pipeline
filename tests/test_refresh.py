import json
import math
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

from scripts.refresh import (
    blank, build_snapshot, date_rows_csv, make_quote, numeric, pct_from_pair,
    collect_crypto, collect_gold, collect_fred, collect_stooq, collect_fed_releases,
)

NOW = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)

class ValidationTests(unittest.TestCase):
    def test_csv_last_two_sorted_and_missing_removed(self):
        rows = date_rows_csv(b"observation_date,VIXCLS\n2026-10-13,15\n2026-10-11,.\n2026-10-12,12\n", "VIXCLS")
        self.assertEqual(rows, [(date(2026,10,12),12.0),(date(2026,10,13),15.0)])
        self.assertEqual(pct_from_pair(rows), 25.0)

    def test_legacy_csv_date_header(self):
        self.assertEqual(date_rows_csv(b"Date,Close\n2026-10-13,170\n", "Close")[-1][1], 170)

    def test_reject_invalid_numeric(self):
        for v in ("nan", "inf", "-12", "0", "99999999999", "not a number"):
            with self.subTest(v=v), self.assertRaises(ValueError):
                numeric(v)

    def test_never_fabricates_eod_time(self):
        q = make_quote("PLTR", 171.54, date(2026,10,13), NOW)
        self.assertEqual(q["as_of"], "2026-10-13")
        self.assertEqual(q["granularity"], "date")
        self.assertEqual(q["verification"], "single_source")

    def test_future_and_stale_guard(self):
        with self.assertRaises(ValueError):
            make_quote("BTC", 60000, NOW + timedelta(hours=1), NOW)
        self.assertEqual(make_quote("BTC", 60000, NOW-timedelta(hours=4), NOW)["quality"], "stale")
        self.assertEqual(make_quote("VIX", 17, date(2026,10,1), NOW)["quality"], "stale")

    def test_gold_real_timestamp(self):
        with patch("scripts.refresh.fetch_json", return_value={"price":4300,"updatedAt":"2026-10-14T11:59:00Z"}):
            q = collect_gold(NOW)
        self.assertEqual(q["quality"], "reported")
        self.assertEqual(q["price"], 4300.0)

    def test_crypto_independent_availability(self):
        payload = {"bitcoin":{"usd":61000,"last_updated_at":int(NOW.timestamp()),"usd_24h_change":-2},
                   "ethereum":{"usd":"nan","last_updated_at":int(NOW.timestamp())}}
        with patch("scripts.refresh.fetch_json", return_value=payload):
            q = collect_crypto(NOW)
        self.assertEqual(q["BTC"]["change_percent"], -2.0)
        self.assertIsNone(q["ETH"])

    def test_stooq_daily_change(self):
        with patch("scripts.refresh.request_bytes", return_value=b"Date,Open,High,Low,Close\n2026-10-12,1,1,1,100\n2026-10-13,1,1,1,110\n"):
            q = collect_stooq(NOW)
        self.assertEqual(q["change_percent"], 10.0)

    def test_stooq_fallback_is_not_mislabeled_daily_close(self):
        from scripts.refresh import request_bytes
        bad = b"Exceeded the daily hits limit"
        quote = b"Symbol,Date,Time,Open,High,Low,Close,Volume,Name,Prev\nPLTR.US,2026-10-13,16:00,165,171,163,170,12345,Palantir,168\n"
        with patch("scripts.refresh.request_bytes", side_effect=[bad,quote]):
            q = collect_stooq(NOW)
        self.assertEqual(q["price"], 170)
        self.assertEqual(q["pricing_basis"], "delayed_market_quote")
        self.assertNotEqual(q["pricing_basis"], "daily_close")
        self.assertEqual(q["verification"], "single_source")

    def test_stooq_fallback_rejects_wrong_ticker(self):
        bad = b"No data"
        wrong = b"Symbol,Date,Time,Open,High,Low,Close\nOTHER.US,2026-10-13,16:00,1,1,1,999\n"
        with patch("scripts.refresh.request_bytes", side_effect=[bad,wrong]):
            with self.assertRaises(ValueError):
                collect_stooq(NOW)

    def test_fred_daily_date_not_realtime(self):
        with patch("scripts.refresh.request_bytes", return_value=b"observation_date,DCOILBRENTEU\n2026-10-13,91.5\n"):
            q = collect_fred("BRENT","DCOILBRENTEU",NOW)
        self.assertEqual(q["pricing_basis"], "daily_spot")
        self.assertEqual(q["granularity"], "date")

    def test_feeds_only_official_recent_links(self):
        xml = b'<rss><channel><item><title>Official release</title><link>https://www.federalreserve.gov/newsevents/pressreleases/a.htm</link><pubDate>Wed, 14 Oct 2026 10:00:00 GMT</pubDate></item><item><title>Bad</title><link>https://attacker.example/x</link><pubDate>Wed, 14 Oct 2026 10:00:00 GMT</pubDate></item></channel></rss>'
        with patch("scripts.refresh.request_bytes", return_value=xml):
            news = collect_fed_releases(NOW)
        self.assertEqual(len(news), 1)

    def test_partial_outage_explicitly_unavailable(self):
        collectors = {
            "PLTR": lambda: make_quote("PLTR",150,date(2026,10,13),NOW),
            "XAUUSD": lambda: 1/0,
            "CRYPTO": lambda: {"BTC":None,"ETH":None},
            "BRENT": lambda: None, "VIX": lambda: None,
            "NEWS": lambda: [],
        }
        snap = build_snapshot(NOW, collectors)
        self.assertEqual(snap["status"], "partial")
        self.assertEqual(snap["quality"]["reported"], 1)
        self.assertEqual(next(x for x in snap["assets"] if x["id"]=="XAUUSD")["price"], None)
        self.assertNotIn("narration", snap)

    def test_fail_closed_when_no_valid_market_data(self):
        collectors = {k:(lambda: None) for k in ("PLTR","XAUUSD","BRENT","VIX")}
        collectors["CRYPTO"] = lambda: {}
        collectors["NEWS"] = lambda: []
        with self.assertRaises(RuntimeError):
            build_snapshot(NOW, collectors)

if __name__ == "__main__":
    unittest.main()

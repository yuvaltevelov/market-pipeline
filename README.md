# Market Pipeline — provenance-first dashboard

RTL Hebrew GitHub Pages dashboard backed by a Python standard-library collector.

**Important:** The previous workflow changed a refresh timestamp while keeping hardcoded prices and geopolitical claims. That false-freshness mechanism has been removed. This application does **not** claim to offer an exchange-certified live quote feed.

## What is actually collected?

| Asset | Source | Price type | Timestamp semantics |
| --- | --- | --- | --- |
| PLTR | [Stooq](https://stooq.com/q/?s=pltr.us) | US stock daily close; **fallback** last reported quote if the historical endpoint fails | Trading **date** only; fallback can be intraday |
| XAU/USD | [Gold-API](https://gold-api.com/docs) | Indicative USD per troy oz | Provider's \`updatedAt\` |
| BTC, ETH | [CoinGecko](https://docs.coingecko.com/reference/simple-price) | Indicative USD spot | Provider's \`last_updated_at\` |
| Brent | [FRED / EIA](https://fred.stlouisfed.org/series/DCOILBRENTEU) | **Brent spot** USD/barrel, daily (not futures) | Observation **date** |
| VIX | [FRED / CBOE](https://fred.stlouisfed.org/series/VIXCLS) | Daily closing index (not intraday) | Observation **date** |
| Official releases | [Federal Reserve RSS](https://www.federalreserve.gov/feeds/press_all.xml) | Verbatim feed titles + links (when available) | RSS publication time |

Public free sources are **single-source reports**, not independently cross-verified. Do not use as executable bids/asks or for automated trading. Providers can be delayed, unavailable or restrict data reuse. A "reported" badge means the observation passed format, age and plausibility checks, **not** independent confirmation.

## Data contract and safety

- \`data/latest.json\` uses schema v2; old hardcoded sample data is rejected.
- Every quote has \`as_of\`, \`granularity\`, \`source\`, \`source_url\`, \`pricing_basis\`, \`quality\`, \`verification\`.
- Stale, future, missing, malformed, NaN, infinite and implausible quotes are rejected or distinctly labeled.
- Gold freshness threshold 1 hour; BTC/ETH 3 hours; PLTR 5 calendar days; Brent/VIX 7 calendar days (weekends/holidays accounted for with tolerant windows).
- If all providers fail, no new snapshot is published; the frontend warns about the last collection time.
- No AI system is allowed to invent market-moving headlines, causes, prices or certainty. The deterministic "collect → validate → explain" pipeline is a rules engine, **not** autonomous AI research or trading agents.
- The Federal Reserve official RSS provides source-linked titles; no unverified news claims are retained.

## Deployment

GitHub Pages from **main / (root)** at https://yuvaltevelov.github.io/market-pipeline/ . The site is static, and the backend runs on GitHub Actions with \`schedule\` every 30 minutes (best effort; GitHub may delay or skip scheduled runs) and \`workflow_dispatch\`. The script commits a *new actual snapshot* after reading external sources, then Pages redeploys through the existing branch-based GitHub Pages configuration. No API key is needed for these sources. No guarantee of continuous uptime or intraday exchange quotes.

To get the first real snapshot immediately, open **Actions → Verified market data refresh → Run workflow** after merging. A current snapshot is only available once this job completes successfully.

## Developer verification

\`\`\`sh
python -m unittest discover -s tests -v
python -m scripts.refresh  # requires network; fails closed if no source works
\`\`\`

CI tests are offline and use canned response fixtures; they **do not** validate live provider availability, pricing accuracy, or rights to redistribute data. Live verification requires a successful collector workflow and manual comparison against source pages.

No portfolio positions, broker credentials or private API keys should ever be committed: this repository and Pages site are public.

## Market Pipeline PRO · Historical research

Open [PRO scanner](https://yuvaltevelov.github.io/market-pipeline/pro.html) for stock, ETF, crypto, FX and commodity-futures watchlists, hourly/daily candles, explainable indicator biases, RVOL, CMF, MFI, OBV direction, liquidity sweep, FVG and breakout pattern flags, and paired-return correlations. Mobile-first and RTL.

**Data sources:** Kraken public REST OHLC candles for BTC/ETH; Yahoo Finance's **unofficial and unauthenticated** chart endpoint for stocks, ETFs, FX and commodity futures. The Yahoo feed can rate-limit, change or block access at any time; it is not a licensed or exchange-certified quote service. Data is source-tagged and never cross-verified by default. Historical prices are not execution quotes. FX tick volume is not assumed equal to exchange trading volume. Index/ETF/futures instruments are named distinctly and not substituted for spot XAU/USD or Brent spot.

**Analysis:** 20/50 EMA, 200 SMA (when possible), Wilder RSI14, ATR14, 20-bar relative volume (excluding current volume from comparison baseline), CMF20, MFI14, OBV direction, 20-bar rolling VWAP (not intraday anchored VWAP), sweep, 20-bar breakout and three-candle FVG. All patterns are *hypotheses*, not manipulation or institutional ownership detection. CVD, level-2 depth, actual aggressive buy/sell transaction classification, institutional holdings, and live options flow are explicitly **unavailable**, not synthesized.

**Backtest:** deterministic, fixed-parameter long-only rules. The final chronological 25% of historical data is treated as holdout; signal at bar close, enter at next bar's open, close after five daily or eight hourly bars at an open, with 20 bps roundtrip friction. No forward knowledge, no leverage/short financing assumed, and no parameter fit on holdout. At least five non-overlapping trades required or outcome is unavailable. This exploratory backtest is not a calibrated win probability, is sensitive to survivorship, fill/slippage assumptions and timeframe selection, and is **not** independently verified trading performance. Review provider rights and test on further out-of-sample sets before relying on it.

**Operations:** \`.github/workflows/pro.yml\` schedules a scan every four hours (best effort) plus manual dispatch and refresh after relevant code merges. Real data refresh must succeed for \`data/pro.json\` to be published; provider outages are explicit. Daily bars are complete only; intraday analysis uses completed hourly bars only; Yahoo hourly queries use its documented 1mo calendar range (not an invalid 60d range). User can modify \`WATCHLIST\` in \`scripts/pro.py\`. Data file is public. Existing basic dashboard remains at \`index.html\`.

**Run offline tests:** \`python -m unittest discover -s tests -v\` and \`node --check assets/pro.js\`. GitHub Actions performs live ingestion testing; external providers may remain unavailable. No keys should be committed.

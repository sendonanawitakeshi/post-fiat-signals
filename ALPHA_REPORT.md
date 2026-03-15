# Alpha Submission: Semi-to-Crypto Lead-Lag Mechanism with Regime-Conditional Filter

**Submitted by**: rfLJ4ZRnqmGFLAcMvCD56nKGbjpdTJmMqo
**Date**: March 2026
**Type**: Quantitative research finding with live infrastructure for network consumption
**Status**: READY — verified March 12, 2026

---

## 1. Core Finding

Semiconductor equities Granger-cause crypto AI token returns at the daily timeframe. The effect is asymmetric, statistically robust, and — when filtered by market regime — produces an actionable trading signal with an 82% hit rate.

### Granger Causality Evidence

i ran Granger causality tests across 5 semiconductor stocks (NVDA, AMD, AVGO, TSM, MRVL) against 4 crypto AI tokens (TAO, RNDR, AKT, FET) using 249 daily log-return observations (250 trading days) spanning March 2025 to March 2026.

**Daily resolution (249 observations, 20 pairs):**
- Semi → Crypto: **20/20 pairs significant** (100%) after Bonferroni correction (p < 0.0025 = 0.05/20)
- Crypto → Semi: **4/20 pairs significant** at p<0.05 uncorrected, **0/20** after Bonferroni
- Average best F-statistic (semi→crypto): **18.57**
- 18/20 pairs at p<0.001, remaining 2 at p<0.003
- Optimal lag: 1 day for 17 of 20 pairs

The asymmetry is overwhelming. Semi stocks Granger-cause crypto AI tokens. The reverse direction shows only 4/20 pairs at uncorrected p<0.05 and none survive Bonferroni. This isnt correlation — its directional causality confirmed by a test designed specifically to detect lead-lag relationships.

**Hourly resolution (202 observations, 9 pairs):**
- Semi → Crypto: **6/9 pairs significant** at p<0.05, but only **1/9 survives Bonferroni** correction (NVDA→RNDR, p=0.0023)
- Crypto → Semi: **0/9 significant** after Bonferroni
- Average best F-statistic: **2.40** (vs 18.57 at daily)

The signal weakens dramatically at hourly resolution. This isnt noise — its a structural property of how information transfers between these markets. More on this in the Mechanism section.

### Regime-Conditional Filter

The raw Granger causality finding is necessary but not sufficient for trading. Aggregate divergence signals across all market regimes produce hit rates around 56% (basically a coin flip). The breakthrough was decomposing by regime AND signal type simultaneously.

Using a 60-day rolling regime classifier (3 states: NEUTRAL, DIVERGENCE, EARNINGS) with a 20% reliability decay threshold, i filtered 87 divergence signals across 251 trading days into 9 regime × signal type combinations:

**NEUTRAL / CRYPTO_LEADS** (the actionable signal):
- Hit rate: **82%** (n=22 signals with 14-day evaluation window)
- Average 14-day return: **+8.24%**
- 95% confidence interval: **[61%–93%]** — CI excludes 50%, statistically significant
- False positive rate: 18%
- Cumulative return across all 22 signals: **+181.3%**

**NEUTRAL / SEMI_LEADS** (the anti-signal):
- Hit rate: **12%** (n=16)
- Average 14-day return: **-14.60%**
- 95% CI: [3%–36%]
- This combination actively destroys capital. When semis lead crypto during NEUTRAL conditions, the divergence corrects against the trade direction 88% of the time.

All other 7 regime × signal type combinations are AMBIGUOUS — either insufficient sample size (n<10) or 95% CI spans 50%.

The filter converts an aggregate coin-flip signal into a binary decision: NEUTRAL + CRYPTO_LEADS = EXECUTE. Everything else = WAIT.

---

## 2. Mechanism Explanation

### Why Daily Works but Hourly Doesnt

The drop from 20/20 Bonferroni significance at daily to 1/9 at hourly reveals the mechanism. This isnt an intraday trading signal — its an accumulation effect.

At the hourly level, information transfers from semi stocks to crypto AI tokens are marginal. Individual hourly returns show weak, inconsistent Granger causality (average F-stat 2.40). But these marginal transfers compound throughout the trading day. By the daily close, the accumulated information transfer is overwhelming (average F-stat 18.57, 100% significance).

The mechanism works like this: institutional semi positioning (earnings expectations, supply chain data, capacity announcements) gradually propagates into crypto AI token pricing through a network of cross-asset traders, algorithmic strategies, and narrative-driven retail flow. The propagation isnt instantaneous — it takes 6-24 hours for the full information content to transfer. This is why the optimal lag is 1 day for 17 of 20 pairs (the remaining 3 have best lags at 2 or 7 days, still within the daily accumulation framework). The semi market closes, the information fully prices into crypto overnight and through the next session, and the Granger test captures the completed transfer.

The strongest hourly signal — NVDA→RNDR at lag 28 (p=0.0023, the only Bonferroni survivor) — corresponds to roughly 4 trading days of accumulated transfer. Even the intraday candidates (NVDA→AKT lag 1, F=5.93; NVDA→RNDR lag 1, F=4.90) dont survive multiple comparison correction. The intraday signal exists but isnt tradeable on its own.

### Why the Regime Filter Works

Aggregate divergence signals fail because SEMI_LEADS signals are anti-signals that drag the average below 50%. During NEUTRAL regimes (67% of the backtest period), SEMI_LEADS had a 12% hit rate — meaning 88% of the time, when semis led crypto in NEUTRAL conditions, the divergence resolved against the predicted direction.

The regime filter works by decomposing the information transfer into its directional components. CRYPTO_LEADS divergences during NEUTRAL regimes capture moments when crypto AI tokens have already begun pricing in the semi information transfer, creating a momentum signal that continues for 14+ days. SEMI_LEADS divergences capture false starts — semis moving on sector-specific news (earnings, guidance, supply chain) that doesnt propagate to crypto because the information is priced in at the semi level but has no crypto-relevant signal content.

The 60-day rolling window for regime detection was selected empirically. Shorter windows (30d) produce too much noise with high false positive rates. Longer windows (90d) lag behind fast-moving regime shifts. The 60-day window achieves 60% regime detection accuracy with a 27-day average lead time — enough to position before the regime fully manifests.

---

## 3. Infrastructure Reference

This research is backed by a complete signal-to-consumer pipeline, publicly available for any Hive Mind contributor to consume programmatically.

### Public SDK

**Repository**: https://github.com/sendoeth/post-fiat-signals

Python SDK (v0.3.0) for consuming regime detection signals in real time. Zero external dependencies, Python 3.10+, auto-retry with exponential backoff, typed dataclasses for all responses. Install and run in under 2 minutes.

Key endpoints accessible via SDK:

| Endpoint | SDK Method | What It Returns |
|----------|-----------|-----------------|
| `/regime/current` | `get_regime_state()` | Current regime classification (NEUTRAL/DIVERGENCE/EARNINGS), confidence, active duration |
| `/signals/filtered` | `get_filtered_signals()` | Regime-gated trade recommendations with per-signal hit rate, avg return, and ACTIONABLE/SUPPRESS/AMBIGUOUS classification |
| `/signals/reliability` | `get_signal_scores()` | Per-asset reliability decay curves for position sizing |
| `/health` | `get_health()` | System health, data freshness, cache age |
| `/regime/history` | `get_regime_history()` | Historical regime transitions for backtesting |
| `/rebalancing/queue` | `get_rebalance_queue()` | Recommended position changes based on current regime |

### Paste-and-Run Integration

See **USE_CASES.md** in the SDK repo for 3 persona-specific code snippets:

1. **Regime-Gated Bot Operator** — binary EXECUTE/WAIT gate using `get_regime_state()` + `get_filtered_signals()`. 15 lines of Python, drops into any existing trading bot.
2. **Decay-Aware Position Sizer** — scales position size by CRYPTO_LEADS reliability decay percentage using `get_signal_scores()`.
3. **Regime Shift Alert Monitor** — cron-based regime change detection with notification hooks using `get_regime_history()` + `get_rebalance_queue()`.

Each snippet is self-contained. Set `PF_API_URL` and run.

### Reliability Guarantees

- **18 stress test scenarios** (`tests/test_stress.py`) covering every failure mode: malformed JSON, empty bodies, HTTP 500/502/503, connection refused, timeouts, partial responses, stale data. All 18 pass.
- **Circuit breaker watchdog** (`examples/watchdog.py`) — 3 independent integrity checks (system health, signal fidelity, regime confidence). Returns VALID/DEGRADED/STOP with exit codes 0/1/2. Shell-chainable: `watchdog.py && regime_scanner.py`.
- **Model drift detector** (`drift_watchdog.py`) — hourly Granger F-stat monitoring with 3 detectors. Catches structural breakdowns in the lead-lag relationship before they contaminate signal output.
- **36 integration tests** covering all 6 API endpoints including degraded state validation.

### Validator Node

Live testnet validator contributing to Post Fiat consensus:
- **Public key**: `nHBcLEB4S6moQGrhMjJo1jbp58WL5psHY9EMDWNAtdqykUYiA1rF`
- **Validator website**: https://sendoeth.github.io/validator/
- **Agreement scores**: 100% (1h), 100% (24h), 99.75% (30d)
- **Running since**: February 14, 2026

---

## 4. Attestation

i attest that:

1. The statistical findings presented in this submission are based on my own original research conducted between March 7-12, 2026.
2. The Granger causality analysis used 249 daily log-return observations (250 trading days, March 2025 to March 2026) and 202 hourly return observations (30 trading days) sourced from Yahoo Finance and CoinGecko.
3. The regime-conditional filter was backtested across 87 divergence signals over 251 trading days using the methodology described in this submission.
4. All hit rates, return figures, confidence intervals, and sample sizes match the primary research outputs stored in my local analysis files.
5. The public SDK repository and all referenced endpoints are live, functional, and accessible without login or paywall.
6. This finding has not been previously submitted as an alpha task to the Post Fiat network.
7. i am a Post Fiat testnet validator (public key: nHBcLEB4S6moQGrhMjJo1jbp58WL5psHY9EMDWNAtdqykUYiA1rF) with 30d agreement score of 99.75%.
8. The infrastructure described in Section 3 is publicly available at https://github.com/sendoeth/post-fiat-signals for any network participant to verify, consume, or build upon.

---

## 5. Submission Readiness Checklist

| Check | Status | Notes |
|-------|--------|-------|
| Cooldown status verified | PENDING | Submit when cooldown lifts. Check via Discord `/status` or wallet activity. |
| All referenced URLs load without login | VERIFIED | SDK repo (200), validator site (200), explorer link (200) — all confirmed March 12, 2026 |
| Finding not previously submitted as alpha | VERIFIED | First alpha submission for this wallet |
| Granger statistics internally consistent | VERIFIED | 20/20 daily (Bonferroni p<0.0025, 18/20 at p<0.001), 1/9 hourly Bonferroni (NVDA→RNDR p=0.0023), avg F-stat 18.57 daily / 2.40 hourly — matches granger_causality_results.md |
| Regime filter stats internally consistent | VERIFIED | 82% hit rate, +8.24% avg return, n=22, CI [61%-93%] — matches regime_conditional_filter.md primary source |
| Anti-signal stats consistent | VERIFIED | SEMI_LEADS 12% hit rate, -14.60% avg return, n=16 — matches source |
| SDK repo has USE_CASES.md with paste-and-run code | VERIFIED | 3 persona-specific snippets present in repo |
| Stress tests pass (18/18) | VERIFIED | All scenarios pass as of v0.3.0 |
| Watchdog functional | VERIFIED | March 12 2026: YELLOW overall (F-Stat GREEN, Lag Shift GREEN, Sig Loss YELLOW — NVDA→RNDR p=0.006 borderline on hourly Bonferroni but all 6 pairs retain p<0.05) |
| Validator node active | VERIFIED | 100% 1h agreement, 100% 24h agreement, 99.75% 30d agreement |
| Writing style matches context document | VERIFIED | No apostrophes, lowercase i, data-dense, abbreviations where natural |

### Pre-Submit Actions

1. Check cooldown status — do NOT submit during active cooldown
2. Run `drift_watchdog.py` to confirm Granger relationship still intact on submission day
3. Verify SDK repo URLs one final time (`curl -s -o /dev/null -w "%{http_code}" https://github.com/sendoeth/post-fiat-signals`)
4. Save updated context document after submission
5. Note submission timestamp for context document cadence tracking

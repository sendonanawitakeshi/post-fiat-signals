# Live Signal STOP State — Root Cause Diagnostic

**Date**: 2026-03-13
**Investigator**: `rfLJ4ZRnqmGFLAcMvCD56nKGbjpdTJmMqo`
**System health surface**: [`status.json`](../status.json)

---

## Summary

The live signal pipeline currently returns **STOP** on every execution. This is **correct protective behavior, not a malfunction**. The root cause is **expected market-state behavior** — specifically, a prolonged period of structural correlation decay across all three signal types that has been underway since August-October 2025. The watchdog thresholds are appropriately calibrated and should not be loosened. The recommendation is to improve STOP-state messaging so first-time builders can distinguish safe halts from broken infrastructure.

---

## 1. Root Cause Category

**Primary cause: Expected market-state behavior**

The STOP state is triggered by real, persistent signal decay across all three Granger-validated correlation types. This decay reflects genuine changes in market correlation structure, not a tuning error or data quality problem.

**Contributing factor: Threshold interaction effects**

Four independent watchdog checks simultaneously trip the STOP threshold, creating a "wall of red" that can look like system failure to a new user. In reality, these four checks are measuring different symptoms of the same underlying condition (market correlation regime shift), so they correctly fire together.

**Not the cause: Threshold miscalibration**

The thresholds are set based on backtested regime detection parameters (20% decay threshold, 60-day optimal window, 40% FP rate). Loosening them would increase false negatives — the system would tell builders to trade on signals that no longer have statistical backing.

**Not the cause: Upstream data quality**

The API is healthy (status: `ok`, data age: <15 min, no errors, 400+ successful refreshes). Yahoo Finance and CoinGecko feeds are operational. The issue is in what the data shows, not in whether the data arrives.

---

## 2. Evidence From Live Test Runs

### Run 1 — 2026-03-13T20:24:34Z

| Component | State | Key Evidence |
|-----------|-------|-------------|
| System Health | VALID | api_status=ok, data_age=214s, is_stale=false, last_error=none |
| Signal Fidelity | **STOP** | 3/3 types decaying, CRYPTO_LEADS drop=50.6% (>40% threshold), regime_alert=triggered |
| Regime Confidence | DEGRADED | confidence=77, regime=SYSTEMIC, is_alert=true, bt_fp_rate=40% |

**Watchdog verdict**: STOP (exit code 2)
**Pipeline verdict**: NO_TRADE (exit code 2)
**Pipeline note**: "signal integrity compromised"

### Run 2 — 2026-03-13T20:26:56Z

| Component | State | Key Evidence |
|-----------|-------|-------------|
| System Health | VALID | api_status=ok, data_age=355s, is_stale=false, last_error=none |
| Signal Fidelity | **STOP** | 3/3 types decaying, CRYPTO_LEADS drop=50.6% (>40% threshold), regime_alert=triggered |
| Regime Confidence | DEGRADED | confidence=77, regime=SYSTEMIC, is_alert=true, bt_fp_rate=40% |

**Watchdog verdict**: STOP (exit code 2)
**Pipeline verdict**: NO_TRADE (exit code 2)
**Pipeline note**: "signal integrity compromised"

### Consistency Across Runs

Both runs produce identical STOP verdicts. The underlying data did not change between runs (same API refresh cycle, timestamp `2026-03-13T20:21:00.851Z`). This confirms the STOP is deterministic and driven by persistent market state, not a transient glitch.

---

## 3. Detailed Signal Decay Analysis

### Current Signal Reliability Scores

| Signal Type | All-Time Score | Current Rolling (30d) | Drop % | Decaying Since | Freshness |
|-------------|---------------|----------------------|--------|----------------|-----------|
| SEMI_LEADS | 68 | 38 | 44.1% | 2025-09-04 | Stale |
| CRYPTO_LEADS | 85 | 42 | 50.6% | 2025-08-13 | Stale |
| FULL_DECOUPLE | 75 | 39 | 48.0% | 2025-10-16 | Stale |

### Why These Numbers Trigger STOP

The watchdog has four independent checks that currently fire at STOP level:

| Check | Threshold | Current Value | Result |
|-------|-----------|---------------|--------|
| Decaying types count | >= 2 types = STOP | 3/3 types decaying | **STOP** |
| CRYPTO_LEADS drop % | >= 40% = STOP | 50.6% | **STOP** |
| CRYPTO_LEADS freshness | "Stale" = STOP | Stale | **STOP** |
| Regime alert | triggered = STOP | triggered (3 types) | **STOP** |

All four are measuring the same underlying phenomenon: the semi-to-crypto lead-lag correlations that existed during the 2025-03 to 2025-08 period have weakened substantially. The decay has been continuous for 5-7 months.

### What The Backtest Data Says About SYSTEMIC Regime

The regime classifier correctly identifies the current state as SYSTEMIC (77% confidence). Under SYSTEMIC regime, the regime-conditional filter shows:

| Signal Type | Classification | Hit Rate | n | Avg Return |
|-------------|---------------|----------|---|------------|
| SEMI_LEADS | SUPPRESS | 10% | 10 | -18.3% |
| CRYPTO_LEADS | SUPPRESS | 20% | 5 | -9.8% |
| FULL_DECOUPLE | SUPPRESS | 25% | 4 | -7.6% |

All signal types are suppressed under SYSTEMIC. Trading any of them would historically produce losses. The system is preventing exactly the trades it should prevent.

For comparison, the only actionable setup from 264 trading days of backtesting:
- **NEUTRAL + CRYPTO_LEADS**: 82% hit rate, +8.24% avg 14d return, n=22

The system correctly blocks trades until market conditions return to NEUTRAL with intact CRYPTO_LEADS correlation.

---

## 4. What A First-Time Builder Sees (The UX Problem)

A builder who clones the repo and runs `python3 examples/full_pipeline_demo.py` against the live API currently sees:

```
STAGE 1: WATCHDOG
Verdict: STOP
  VALID      System Health
  STOP       Signal Fidelity
  DEGRADED   Regime Confidence

STAGE 3: TRADE DECISION
NO_TRADE  (0 execute, 0 wait)
Note: signal integrity compromised

Exit code: 2
```

The problem is not the verdict — the verdict is correct. The problem is that "SIGNAL INTEGRITY COMPROMISED" and "signal integrity compromised" sound like the infrastructure is broken. A new builder cannot tell from this output whether:

1. The system detected dangerous market conditions and is protecting them (correct interpretation)
2. The API is misconfigured or the data pipeline is broken (incorrect interpretation)

The mock server deliberately returns NEUTRAL-regime data with healthy signals, so `full_pipeline_demo.py` against the mock produces EXECUTE_REDUCED. This contrast makes the live STOP look even more like a bug.

---

## 5. Recommendation

### Do NOT change the watchdog thresholds

The thresholds are correctly calibrated:
- 20% decay threshold matches the backtested regime detection parameter
- 40% CRYPTO_LEADS drop threshold is set at the level where the primary trading edge is statistically unreliable
- 2-type decay minimum for STOP matches the regime alert trigger
- These thresholds prevented trading during a period where all signal types show negative expected returns

Loosening thresholds would create false confidence. The system would tell builders to trade when the statistical edge is gone.

### Do NOT add upstream fallbacks

The upstream data sources (Yahoo Finance, CoinGecko) are working correctly. The signal decay reflects real market behavior, not data feed failure. Adding fallback sources would not change the decay measurements because the decay is in the correlations, not in the price data.

### DO improve STOP-state messaging

The concrete next step is to make the STOP output clearly communicate that it is protective behavior. Specific changes:

**1. Replace "SIGNAL INTEGRITY COMPROMISED" language**

Current wording implies the system is broken. Better framing:

```
VERDICT: HALT — No actionable signals in current market regime

The system detected that historical trading correlations have weakened
beyond the safety threshold. This is protective behavior, not a malfunction.

Current regime: SYSTEMIC (77% confidence)
All 3 signal types: decaying for 5-7 months
CRYPTO_LEADS: dropped 50.6% from all-time reliability

Under SYSTEMIC regime, all signal types historically produce losses.
The system will generate EXECUTE signals when market conditions return
to NEUTRAL with intact CRYPTO_LEADS correlation.

See: status.json for real-time health state
See: docs/STOP_STATE_DIAGNOSTIC.md for full analysis
```

**2. Add "what happens next" to pipeline output**

Builders seeing STOP need to know: is this permanent? What would change it? Add one line:

```
The system will return to EXECUTE when the regime shifts back to NEUTRAL
and CRYPTO_LEADS reliability recovers above the 40% decay threshold.
```

**3. Link the diagnostic from status.json**

Add a `diagnostic_url` field to the status.json output when overall_health is HALT, pointing to this document.

---

## 6. Status

This diagnostic confirms that the live STOP state is the correct system response to current market conditions. The signal infrastructure is working as designed. The gap is in first-use messaging, not in signal quality or threshold calibration.

### System Health Surface

- **Static**: [`status.json`](../status.json) — auto-updated every 15 minutes
- **Live**: `GET http://<your-server-ip>:8080/system/status` — real-time
- **Repo**: [github.com/sendoeth/post-fiat-signals](https://github.com/sendoeth/post-fiat-signals)

### Raw Evidence Archive

Full endpoint payloads from both test runs are archived in the investigation notes. Key timestamps:
- Run 1: 2026-03-13T20:24:34Z (watchdog exit 2, pipeline exit 2)
- Run 2: 2026-03-13T20:26:56Z (watchdog exit 2, pipeline exit 2)
- API data timestamp: 2026-03-13T20:21:00.851Z (refresh #2, 411+ total since last restart)
- API uptime at time of test: 18-21 minutes (fresh restart, prior uptime was 102+ hours)

#!/usr/bin/env python3
"""Signal Integrity Watchdog — VALID/INVALID pre-trade validation.

Polls the Signal Intelligence API via the SDK and checks whether the
semi-crypto lead-lag relationship is still intact before you open positions.

Three checks:
  1. Signal Decay — are CRYPTO_LEADS reliability scores degrading?
  2. Regime Stability — is the regime classification confident and stable?
  3. Filter Integrity — do live hit rates still match backtested baselines?

If any check fails, the verdict is INVALID and you should not open new
positions based on these signals until the issue resolves.

Usage:
    export PF_API_URL=http://your-node:8080
    python3 watchdog.py

    # or pass directly
    python3 watchdog.py --url http://your-node:8080
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pf_regime_sdk import RegimeClient


# ── Baselines (from 264 trading days of backtesting) ────────────────────────

# Regime-filter hit rates under NEUTRAL (the reference regime)
BASELINE_HIT_RATES = {
    "CRYPTO_LEADS":  0.82,   # 82% — the single actionable setup
    "SEMI_LEADS":    0.12,   # 12% — anti-signal
    "FULL_DECOUPLE": 0.50,   # 50% — coin flip
}

# Regime detection baselines
BASELINE_ACCURACY = 60.0     # % accuracy at 60d optimal window
BASELINE_FP_RATE = 40.5      # % false positive rate
BASELINE_LEAD_TIME = 27.3    # trading days average lead time

# Thresholds
DECAY_DROP_THRESHOLD = 20.0  # % drop from all-time = decaying
MIN_CONFIDENCE = 50          # regime confidence floor
MAX_HIT_RATE_DRIFT = 0.20    # 20pp max deviation from baseline
CRYPTO_LEADS_FLOOR = 0.50    # absolute floor for CRYPTO_LEADS hit rate


# ── Three checks ────────────────────────────────────────────────────────────

def check_signal_decay(reliability):
    """Check 1: Is CRYPTO_LEADS reliability decaying?

    If the primary signal type shows reliability decay (rolling score
    dropped 20%+ from all-time), the Granger-validated lead-lag
    relationship may be breaking down.
    """
    cl = reliability.types.get("CRYPTO_LEADS")
    if not cl:
        return "INVALID", "CRYPTO_LEADS not found in reliability data", {}

    detail = {
        "score": cl.score,
        "all_time": cl.all_time_score,
        "current_rolling": cl.current_rolling,
        "drop_pct": cl.drop_pct,
        "is_decaying": cl.is_decaying,
        "freshness": cl.freshness,
    }

    # Check if any signal types are decaying
    decaying_types = [t for t, s in reliability.types.items() if s.is_decaying]
    detail["decaying_types"] = decaying_types
    detail["regime_alert"] = reliability.regime_alert

    if cl.is_decaying:
        return ("INVALID",
                f"CRYPTO_LEADS reliability decaying: score dropped {cl.drop_pct:.1f}% "
                f"from all-time ({cl.all_time_score} -> {cl.current_rolling})",
                detail)

    if len(decaying_types) >= 2:
        return ("INVALID",
                f"{len(decaying_types)} signal types decaying ({', '.join(decaying_types)}) "
                f"— potential regime shift underway",
                detail)

    return "VALID", f"CRYPTO_LEADS stable (score={cl.score}, drop={cl.drop_pct:.1f}%)", detail


def check_regime_stability(regime):
    """Check 2: Is the regime classification confident and stable?

    Low confidence means the regime detector is uncertain — the optimal
    detection window may be shifting, which degrades signal quality.
    """
    detail = {
        "regime_id": regime.regime_id,
        "regime_type": regime.regime_type,
        "confidence": regime.confidence_score,
        "is_alert": regime.is_alert,
    }

    if regime.backtest_context:
        bt = regime.backtest_context
        detail["accuracy"] = bt.accuracy
        detail["fp_rate"] = bt.fp_rate
        detail["avg_lead_time"] = bt.avg_lead_time
        detail["optimal_window"] = bt.optimal_window

        # Check if accuracy has degraded significantly
        accuracy_delta = abs(bt.accuracy - BASELINE_ACCURACY)
        if accuracy_delta > 15:
            return ("INVALID",
                    f"Regime detection accuracy shifted {accuracy_delta:.0f}pp "
                    f"from baseline ({bt.accuracy:.0f}% vs {BASELINE_ACCURACY:.0f}%)",
                    detail)

    if regime.confidence_score < MIN_CONFIDENCE:
        return ("INVALID",
                f"Regime confidence {regime.confidence_score} below {MIN_CONFIDENCE} threshold "
                f"— classification unreliable",
                detail)

    return ("VALID",
            f"Regime {regime.regime_id} (conf={regime.confidence_score}) — stable",
            detail)


def check_filter_integrity(filtered):
    """Check 3: Do current regime-filter hit rates match baselines?

    Compares the live filter rules against backtested NEUTRAL baselines.
    Large deviations mean the model is drifting from validated performance.
    """
    detail = {
        "current_regime": filtered.regime_id,
        "types": {},
    }

    # Use NEUTRAL baselines as reference regardless of current regime
    max_drift = 0
    cl_hit_rate = None

    for sig_type, baseline_rate in BASELINE_HIT_RATES.items():
        rule = filtered.filter_rules.get(sig_type)
        if not rule:
            continue

        live_rate = rule.hit_rate
        drift = abs(live_rate - baseline_rate)
        if drift > max_drift:
            max_drift = drift

        if sig_type == "CRYPTO_LEADS":
            cl_hit_rate = live_rate

        detail["types"][sig_type] = {
            "live_rate": live_rate,
            "baseline_rate": baseline_rate,
            "drift": round(drift, 4),
            "drift_pp": round(drift * 100, 1),
            "classification": rule.classification,
        }

    detail["max_drift_pp"] = round(max_drift * 100, 1)

    # Under non-NEUTRAL regimes, hit rates will differ from NEUTRAL baselines
    # by design. Only flag if we're in NEUTRAL and rates are off.
    if filtered.regime_id == "NEUTRAL":
        if cl_hit_rate is not None and cl_hit_rate < CRYPTO_LEADS_FLOOR:
            return ("INVALID",
                    f"CRYPTO_LEADS hit rate collapsed to {cl_hit_rate:.0%} "
                    f"(floor={CRYPTO_LEADS_FLOOR:.0%})",
                    detail)

        if max_drift > MAX_HIT_RATE_DRIFT:
            return ("INVALID",
                    f"Max hit rate drift {max_drift*100:.0f}pp exceeds "
                    f"{MAX_HIT_RATE_DRIFT*100:.0f}pp threshold",
                    detail)

    return ("VALID",
            f"Filter rules consistent (max drift={max_drift*100:.1f}pp, "
            f"regime={filtered.regime_id})",
            detail)


# ── CLI output ──────────────────────────────────────────────────────────────

def print_report(checks, regime, filtered, reliability):
    pad = lambda s, n: (str(s) + " " * n)[:n]

    all_valid = all(c[0] == "VALID" for c in checks)
    verdict = "VALID" if all_valid else "INVALID"
    verdict_color = "\033[32m" if all_valid else "\033[31m"

    print()
    print("=" * 66)
    print("  SIGNAL INTEGRITY WATCHDOG — Pre-Trade Validation")
    print("=" * 66)
    print()
    print(f"  Regime: {regime.regime_id} ({regime.regime_type})")
    print(f"  Confidence: {regime.confidence_score}")
    print(f"  Timestamp: {regime.timestamp}")
    print()

    labels = ["Signal Decay", "Regime Stability", "Filter Integrity"]
    for i, (status, reason, detail) in enumerate(checks):
        color = "\033[32m" if status == "VALID" else "\033[31m"
        print(f"  {color}{pad(status, 8)}\033[0m {labels[i]}")
        print(f"           {reason}")
        print()

    print("  " + "-" * 62)
    print(f"  VERDICT: {verdict_color}{verdict}\033[0m")
    print()

    if verdict == "VALID":
        print("  Signal integrity confirmed. Lead-lag relationship intact.")
        print("  Safe to evaluate EXECUTE/WAIT via regime_scanner.py.")
    else:
        print("  Signal integrity degraded. DO NOT open new positions.")
        print("  Re-run after conditions stabilize.")
    print()

    # Baselines reference
    print("  " + "-" * 62)
    print("  Baseline Reference (264 trading days):")
    print(f"    CRYPTO_LEADS hit rate: {BASELINE_HIT_RATES['CRYPTO_LEADS']:.0%}")
    print(f"    Regime accuracy: {BASELINE_ACCURACY:.0f}%")
    print(f"    Decay threshold: {DECAY_DROP_THRESHOLD:.0f}% drop from all-time")
    print(f"    Min confidence: {MIN_CONFIDENCE}")
    print()


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    url_arg = None
    for arg in sys.argv[1:]:
        if arg.startswith("--url="):
            url_arg = arg.split("=", 1)[1]
        elif arg == "--url" and sys.argv.index(arg) + 1 < len(sys.argv):
            url_arg = sys.argv[sys.argv.index(arg) + 1]

    api_url = url_arg or os.environ.get("PF_API_URL", "http://localhost:8080")
    client = RegimeClient(base_url=api_url, timeout=15)

    print(f"Connecting to {api_url}...")

    try:
        regime = client.get_regime_state()
        reliability = client.get_signal_scores()
        filtered = client.get_filtered_signals()

        check1 = check_signal_decay(reliability)
        check2 = check_regime_stability(regime)
        check3 = check_filter_integrity(filtered)

        print_report([check1, check2, check3], regime, filtered, reliability)

    except Exception as e:
        print(f"\nERROR: {type(e).__name__}: {e}")
        print(f"\nMake sure the Signal Intelligence API is running at {api_url}")
        print("Start it with: node signal_api.js")
        sys.exit(1)


if __name__ == "__main__":
    main()

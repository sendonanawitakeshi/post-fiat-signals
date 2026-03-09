#!/usr/bin/env python3
"""Regime Scanner — EXECUTE/WAIT decision engine for semi-crypto divergence signals.

Connects to a Post Fiat Signal Intelligence API node, pulls the current regime
state and filtered signals, and maps them to a binary EXECUTE or WAIT decision
based on backtested regime-conditional hit rates.

The single actionable setup:
  - Regime: NEUTRAL
  - Signal type: CRYPTO_LEADS
  - Filter classification: ACTIONABLE
  - Hit rate: >= 65% (baseline 82%, degraded threshold 65%)
  - Reliability: not decaying

Everything else is WAIT. SEMI_LEADS under NEUTRAL is an anti-signal (12% hit
rate, -14.60% avg return). SYSTEMIC regime suppresses all signal types.

Usage:
    export PF_API_URL=http://your-node:8080
    python3 regime_scanner.py

    # or pass directly
    python3 regime_scanner.py --url http://your-node:8080
"""

import os
import sys

# Add parent dir so we can import the SDK when running from examples/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pf_regime_sdk import RegimeClient, FilteredSignalReport, ReliabilityReport


# ── Decision thresholds (from backtested research) ──────────────────────────

ACTIONABLE_REGIME = "NEUTRAL"           # only regime with positive-EV signals
ACTIONABLE_TYPE = "CRYPTO_LEADS"        # only type with reliable hit rate
MIN_HIT_RATE = 0.65                     # baseline 0.82, degraded floor
ANTI_SIGNAL_TYPES = {"SEMI_LEADS"}      # known negative-EV under NEUTRAL
SUPPRESS_REGIMES = {"SYSTEMIC"}         # suppress all signals


# ── Decision engine ─────────────────────────────────────────────────────────

def evaluate(filtered: FilteredSignalReport, reliability: ReliabilityReport):
    """Map API state to EXECUTE/WAIT decisions per signal.

    Returns list of dicts with decision, reason, and signal detail.
    """
    decisions = []
    regime = filtered.regime_id

    # Gate 1: regime-level suppression
    if regime in SUPPRESS_REGIMES:
        decisions.append({
            "decision": "WAIT",
            "reason": f"Regime {regime} (conf={filtered.regime_confidence}) suppresses all signals",
            "gate": "REGIME",
            "signal": None,
        })
        # Still evaluate individual signals for visibility, but all are WAIT
        for sig in filtered.signals:
            decisions.append({
                "decision": "WAIT",
                "reason": f"Suppressed by {regime} regime",
                "gate": "REGIME",
                "signal": sig,
            })
        return decisions

    # Gate 2: non-NEUTRAL regime — signals are ambiguous
    if regime != ACTIONABLE_REGIME:
        for sig in filtered.signals:
            decisions.append({
                "decision": "WAIT",
                "reason": f"Regime {regime} is not NEUTRAL — signals are ambiguous",
                "gate": "REGIME",
                "signal": sig,
            })
        if not filtered.signals:
            decisions.append({
                "decision": "WAIT",
                "reason": f"Regime {regime} is not NEUTRAL — no actionable setups",
                "gate": "REGIME",
                "signal": None,
            })
        return decisions

    # Gate 3: per-signal evaluation under NEUTRAL
    if not filtered.signals:
        decisions.append({
            "decision": "WAIT",
            "reason": "NEUTRAL regime but no active divergence signals",
            "gate": "NO_SIGNALS",
            "signal": None,
        })
        return decisions

    for sig in filtered.signals:
        # Anti-signal check
        if sig.signal_type in ANTI_SIGNAL_TYPES:
            decisions.append({
                "decision": "WAIT",
                "reason": f"{sig.signal_type} is an anti-signal under NEUTRAL (12% hit rate, -14.60% avg return)",
                "gate": "ANTI_SIGNAL",
                "signal": sig,
            })
            continue

        # Type check
        if sig.signal_type != ACTIONABLE_TYPE:
            decisions.append({
                "decision": "WAIT",
                "reason": f"{sig.signal_type} is not {ACTIONABLE_TYPE} — ambiguous expectancy",
                "gate": "WRONG_TYPE",
                "signal": sig,
            })
            continue

        # Filter classification check
        if sig.regime_filter != "ACTIONABLE":
            decisions.append({
                "decision": "WAIT",
                "reason": f"CRYPTO_LEADS classified as {sig.regime_filter}, not ACTIONABLE",
                "gate": "FILTER",
                "signal": sig,
            })
            continue

        # Hit rate check
        if sig.regime_filter_hit_rate < MIN_HIT_RATE:
            decisions.append({
                "decision": "WAIT",
                "reason": f"Hit rate {sig.regime_filter_hit_rate:.0%} below {MIN_HIT_RATE:.0%} threshold",
                "gate": "HIT_RATE",
                "signal": sig,
            })
            continue

        # Reliability check
        rel = reliability.types.get(ACTIONABLE_TYPE)
        if rel and rel.is_decaying:
            decisions.append({
                "decision": "WAIT",
                "reason": f"CRYPTO_LEADS reliability decaying (drop={rel.drop_pct:.1f}%)",
                "gate": "DECAY",
                "signal": sig,
            })
            continue

        # All gates passed
        decisions.append({
            "decision": "EXECUTE",
            "reason": (f"NEUTRAL + CRYPTO_LEADS + ACTIONABLE | "
                       f"hit={sig.regime_filter_hit_rate:.0%} "
                       f"avg_ret={sig.regime_filter_avg_ret:+.2f}% "
                       f"n={sig.regime_filter_n}"),
            "gate": "PASSED",
            "signal": sig,
        })

    return decisions


# ── CLI output ──────────────────────────────────────────────────────────────

def print_report(filtered: FilteredSignalReport, reliability: ReliabilityReport, decisions: list):
    pad = lambda s, n: (str(s) + " " * n)[:n]

    print()
    print("=" * 70)
    print("  REGIME SCANNER — Semi-Crypto Divergence Decision Engine")
    print("=" * 70)
    print()

    # Regime context
    print(f"  Regime: {filtered.regime_id} ({filtered.regime_label})")
    print(f"  Confidence: {filtered.regime_confidence}")
    print(f"  Active signals: {filtered.total_signals}")
    print(f"  Timestamp: {filtered.timestamp}")
    print()

    # Filter rules for current regime
    print("  Filter Rules (current regime):")
    for t, rule in filtered.filter_rules.items():
        print(f"    {pad(t, 16)} {pad(rule.classification, 12)} "
              f"hit={rule.hit_rate:.0%}  n={rule.n}  avg_ret={rule.avg_ret:+.2f}%")
    print()

    # Decisions
    has_execute = any(d["decision"] == "EXECUTE" for d in decisions)
    summary = "EXECUTE" if has_execute else "WAIT"
    color = "\033[32m" if has_execute else "\033[33m"

    print(f"  Overall: {color}{summary}\033[0m")
    print()

    if not decisions:
        print("  No signals to evaluate.")
    else:
        print("  " + "-" * 66)
        for d in decisions:
            marker = "\033[32mEXECUTE\033[0m" if d["decision"] == "EXECUTE" else "\033[33m  WAIT \033[0m"
            sig = d["signal"]
            if sig:
                print(f"  {marker}  {pad(sig.pair, 14)} [{pad(sig.signal_type, 14)}] conv={sig.conviction}")
            else:
                print(f"  {marker}  (regime-level)")
            print(f"           {d['reason']}")
            print()

    # Decision tree reference
    print("  " + "-" * 66)
    print("  Decision Tree:")
    print("    1. Regime = SYSTEMIC?        -> WAIT (all signals suppressed)")
    print("    2. Regime != NEUTRAL?        -> WAIT (signals ambiguous)")
    print("    3. Type = SEMI_LEADS?        -> WAIT (anti-signal, 12% hit rate)")
    print("    4. Type != CRYPTO_LEADS?     -> WAIT (ambiguous expectancy)")
    print("    5. Filter != ACTIONABLE?     -> WAIT (regime filter says no)")
    print("    6. Hit rate < 65%?           -> WAIT (degraded below threshold)")
    print("    7. Reliability decaying?     -> WAIT (signal going stale)")
    print("    8. All gates passed          -> EXECUTE")
    print()


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    # Resolve API URL
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
        # Fetch data
        filtered = client.get_filtered_signals()
        reliability = client.get_signal_scores()

        # Run decision engine
        decisions = evaluate(filtered, reliability)

        # Print report
        print_report(filtered, reliability, decisions)

    except Exception as e:
        print(f"\nERROR: {type(e).__name__}: {e}")
        print(f"\nMake sure the Signal Intelligence API is running at {api_url}")
        print("Start it with: node signal_api.js")
        sys.exit(1)


if __name__ == "__main__":
    main()

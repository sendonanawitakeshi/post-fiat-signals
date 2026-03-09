#!/usr/bin/env python3
"""Circuit Breaker Watchdog — pre-trade signal integrity check.

Polls the Signal Intelligence API and checks system health and signal
fidelity using server-computed metadata. Returns a VALID, DEGRADED, or
STOP verdict with a corresponding exit code.

Exit codes:
  0 = VALID      — all checks pass, safe to trade
  1 = DEGRADED   — warning conditions, proceed with caution
  2 = STOP       — signal integrity compromised, do not trade

Usage:
    export PF_API_URL=http://your-node:8080
    python3 watchdog.py

    # or pass directly
    python3 watchdog.py --url http://your-node:8080

    # use exit code in scripts
    python3 watchdog.py && python3 regime_scanner.py
"""

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pf_regime_sdk import RegimeClient


# ── Thresholds ──────────────────────────────────────────────────────────────

STALE_WARNING_SEC = 900      # 15 min — data may be one refresh behind
STALE_CRITICAL_SEC = 1800    # 30 min — data is definitely stale
MIN_CONFIDENCE = 50          # regime classifier confidence floor
DECAY_TYPES_WARN = 1         # 1 type decaying = warning
DECAY_TYPES_STOP = 2         # 2+ types decaying = regime shift underway
CRYPTO_LEADS_DROP_WARN = 20  # % drop from all-time = warning
CRYPTO_LEADS_DROP_STOP = 40  # % drop from all-time = stop


# ── Circuit Breaker Checks ──────────────────────────────────────────────────

def check_system_health(health):
    """Check 1: Is the API pipeline functional?

    Parses: status, dataAgeSec, isStale, lastError, dataFresh
    """
    checks = []

    # API status
    if health.status == "warming":
        return "STOP", "API still warming up — cache not loaded", [
            ("api_status", health.status, "STOP")]
    if health.status != "ok":
        checks.append(("api_status", health.status, "DEGRADED"))
    else:
        checks.append(("api_status", health.status, "VALID"))

    # Data freshness
    age = health.data_age_sec or 0
    if age > STALE_CRITICAL_SEC:
        checks.append(("data_age", f"{age}s (>{STALE_CRITICAL_SEC}s)", "STOP"))
    elif age > STALE_WARNING_SEC:
        checks.append(("data_age", f"{age}s (>{STALE_WARNING_SEC}s)", "DEGRADED"))
    else:
        checks.append(("data_age", f"{age}s", "VALID"))

    # Staleness flag
    if health.is_stale:
        checks.append(("is_stale", "true", "STOP"))
    else:
        checks.append(("is_stale", "false", "VALID"))

    # Last error
    if health.last_error:
        checks.append(("last_error", health.last_error[:60], "DEGRADED"))
    else:
        checks.append(("last_error", "none", "VALID"))

    # Data loaded
    if not health.data_fresh:
        checks.append(("data_fresh", "false", "STOP"))
    else:
        checks.append(("data_fresh", "true", "VALID"))

    worst = _worst(checks)
    reason = _summarize(checks, worst)
    return worst, reason, checks


def check_signal_fidelity(reliability):
    """Check 2: Are signal reliability scores intact?

    Parses: isDecaying per type, dropPct, regimeAlert.triggered
    """
    checks = []

    # Count decaying signal types
    decaying = []
    for sig_type, sig in reliability.types.items():
        if sig.is_decaying:
            decaying.append(sig_type)

    if len(decaying) >= DECAY_TYPES_STOP:
        checks.append(("decaying_types", f"{len(decaying)}/3 ({', '.join(decaying)})", "STOP"))
    elif len(decaying) >= DECAY_TYPES_WARN:
        checks.append(("decaying_types", f"{len(decaying)}/3 ({', '.join(decaying)})", "DEGRADED"))
    else:
        checks.append(("decaying_types", "0/3", "VALID"))

    # CRYPTO_LEADS specifically (the primary signal)
    cl = reliability.types.get("CRYPTO_LEADS")
    if cl:
        drop = cl.drop_pct
        if drop >= CRYPTO_LEADS_DROP_STOP:
            checks.append(("crypto_leads_drop", f"{drop:.1f}% (>{CRYPTO_LEADS_DROP_STOP}%)", "STOP"))
        elif drop >= CRYPTO_LEADS_DROP_WARN:
            checks.append(("crypto_leads_drop", f"{drop:.1f}% (>{CRYPTO_LEADS_DROP_WARN}%)", "DEGRADED"))
        else:
            checks.append(("crypto_leads_drop", f"{drop:.1f}%", "VALID"))

        checks.append(("crypto_leads_freshness", cl.freshness,
                        "STOP" if cl.freshness == "Stale" else "VALID"))

    # Regime alert (server-side: 2+ types decaying = regime shift)
    alert = reliability.regime_alert
    if alert.get("triggered"):
        checks.append(("regime_alert", f"triggered ({alert.get('count', 0)} types)", "STOP"))
    else:
        checks.append(("regime_alert", "clear", "VALID"))

    worst = _worst(checks)
    reason = _summarize(checks, worst)
    return worst, reason, checks


def check_regime_confidence(regime):
    """Check 3: Is the regime classification trustworthy?

    Parses: confidence, isAlert, backtestContext.accuracy
    """
    checks = []

    conf = regime.confidence_score
    if conf < MIN_CONFIDENCE:
        checks.append(("confidence", f"{conf} (<{MIN_CONFIDENCE})", "DEGRADED"))
    else:
        checks.append(("confidence", str(conf), "VALID"))

    checks.append(("regime", regime.regime_id, "VALID"))
    checks.append(("is_alert", str(regime.is_alert),
                    "DEGRADED" if regime.is_alert else "VALID"))

    if regime.backtest_context:
        bt = regime.backtest_context
        checks.append(("bt_accuracy", f"{bt.accuracy:.0f}%", "VALID"))
        checks.append(("bt_fp_rate", f"{bt.fp_rate:.0f}%",
                        "DEGRADED" if bt.fp_rate > 50 else "VALID"))

    worst = _worst(checks)
    reason = _summarize(checks, worst)
    return worst, reason, checks


# ── Helpers ─────────────────────────────────────────────────────────────────

SEVERITY = {"VALID": 0, "DEGRADED": 1, "STOP": 2}

def _worst(checks):
    max_sev = max(SEVERITY[c[2]] for c in checks)
    return ["VALID", "DEGRADED", "STOP"][max_sev]

def _summarize(checks, worst):
    if worst == "VALID":
        return "all checks passed"
    failing = [c for c in checks if c[2] == worst]
    return "; ".join(f"{c[0]}={c[1]}" for c in failing)


# ── CLI Output ──────────────────────────────────────────────────────────────

EXIT_CODES = {"VALID": 0, "DEGRADED": 1, "STOP": 2}

VERDICT_LABELS = {
    "VALID": "VALID — safe to trade",
    "DEGRADED": "DEGRADED — proceed with caution",
    "STOP": "STOP: SIGNAL INTEGRITY COMPROMISED",
}

def print_report(results, ts):
    pad = lambda s, n: (str(s) + " " * n)[:n]

    verdicts = [r[0] for r in results]
    overall = "STOP" if "STOP" in verdicts else ("DEGRADED" if "DEGRADED" in verdicts else "VALID")
    exit_code = EXIT_CODES[overall]

    colors = {"VALID": "\033[32m", "DEGRADED": "\033[33m", "STOP": "\033[31m"}
    reset = "\033[0m"

    print()
    print("=" * 66)
    print("  CIRCUIT BREAKER — Signal Integrity Watchdog")
    print("=" * 66)
    print(f"  Timestamp: {ts}")
    print()

    labels = ["System Health", "Signal Fidelity", "Regime Confidence"]
    for i, (status, reason, checks) in enumerate(results):
        c = colors[status]
        print(f"  {c}{pad(status, 10)}{reset} {labels[i]}")
        for name, value, sev in checks:
            sc = colors[sev]
            print(f"             {pad(name, 22)} {sc}{value}{reset}")
        print()

    print("  " + "-" * 62)
    vc = colors[overall]
    print(f"  VERDICT: {vc}{VERDICT_LABELS[overall]}{reset}")
    print(f"  EXIT CODE: {exit_code}")
    print()

    if overall == "VALID":
        print("  Pipeline intact. Run regime_scanner.py for trade decisions.")
    elif overall == "DEGRADED":
        print("  Warning conditions detected. Signals may be unreliable.")
        print("  Reduce position sizes or wait for resolution.")
    else:
        print("  SIGNAL INTEGRITY COMPROMISED. Do NOT open new positions.")
        print("  Investigate degraded dimensions before resuming.")
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
        health = client.get_health()
        reliability = client.get_signal_scores()
        regime = client.get_regime_state()
    except Exception as e:
        print(f"\n  \033[31mSTOP\033[0m  API unreachable: {type(e).__name__}: {e}")
        print(f"\n  Make sure the Signal Intelligence API is running at {api_url}")
        sys.exit(2)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    r1 = check_system_health(health)
    r2 = check_signal_fidelity(reliability)
    r3 = check_regime_confidence(regime)

    print_report([r1, r2, r3], ts)

    overall = "STOP" if "STOP" in [r1[0], r2[0], r3[0]] else (
        "DEGRADED" if "DEGRADED" in [r1[0], r2[0], r3[0]] else "VALID")
    sys.exit(EXIT_CODES[overall])


if __name__ == "__main__":
    main()

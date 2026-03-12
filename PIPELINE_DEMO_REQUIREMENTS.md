# Requirements: `examples/full_pipeline_demo.py`

**Author**: rfLJ4ZRnqmGFLAcMvCD56nKGbjpdTJmMqo
**Date**: March 12, 2026
**Repo**: https://github.com/sendonanawitakeshi/post-fiat-signals
**Status**: Requirements finalized — ready to implement

---

## 1. End-to-End Execution Flow

the demo script chains three existing modules into a single executable flow. each stage gates the next — if a stage fails, the pipeline halts with a clear reason and exit code.

### Stage 1: Watchdog (circuit breaker)

**Module**: `examples/watchdog.py` logic
**SDK calls**: `client.get_health()`, `client.get_signal_scores()`, `client.get_regime_state()`
**Purpose**: pre-trade safety check — is the API up, is the data fresh, are signals intact?

3 independent checks:
1. **System Health** — API status, data age, staleness flag, last error, data freshness
2. **Signal Fidelity** — decay count across signal types, CRYPTO_LEADS drop %, regime alert
3. **Regime Confidence** — classifier confidence score, alert status, backtest accuracy

**Outputs**: VALID (exit 0), DEGRADED (exit 1), or STOP (exit 2)
**Gate rule**: STOP → halt pipeline, print reason, exit 2. DEGRADED → print warning, continue with caution flag. VALID → proceed.

### Stage 2: Regime Scanner (decision engine)

**Module**: `examples/regime_scanner.py` logic
**SDK calls**: `client.get_filtered_signals()`, `client.get_signal_scores()`
**Purpose**: map current regime + active signals to EXECUTE or WAIT per pair

7-gate decision tree (evaluated per signal):
1. Regime = SYSTEMIC? → WAIT (all signals suppressed)
2. Regime != NEUTRAL? → WAIT (signals ambiguous)
3. Signal type = SEMI_LEADS? → WAIT (anti-signal: 12% hit rate, -14.60% avg return)
4. Signal type != CRYPTO_LEADS? → WAIT (ambiguous expectancy)
5. Filter classification != ACTIONABLE? → WAIT
6. Hit rate < 65%? → WAIT (degraded below threshold)
7. CRYPTO_LEADS reliability decaying? → WAIT

All gates passed → **EXECUTE**

**Outputs**: list of per-signal decisions with reason and gate that triggered

### Stage 3: Trade Decision Summary

**Purpose**: synthesize watchdog + scanner into a final actionable output

**Logic**:
- if watchdog = STOP → overall = NO_TRADE, reason = "signal integrity compromised"
- if watchdog = DEGRADED + scanner has EXECUTE signals → overall = EXECUTE_REDUCED, include position sizing note ("reduce size due to degraded conditions")
- if watchdog = VALID + scanner has EXECUTE signals → overall = EXECUTE
- if scanner has zero EXECUTE signals → overall = NO_TRADE, reason from scanner gate

**Output format** (printed to stdout + written to JSON):

```json
{
  "timestamp": "2026-03-12T14:30:00Z",
  "pipeline_version": "1.0.0",
  "watchdog": {
    "verdict": "VALID",
    "system_health": "VALID",
    "signal_fidelity": "VALID",
    "regime_confidence": "VALID"
  },
  "scanner": {
    "regime": "NEUTRAL",
    "confidence": 72,
    "total_signals": 5,
    "decisions": [
      {
        "pair": "NVDA/RNDR",
        "signal_type": "CRYPTO_LEADS",
        "decision": "EXECUTE",
        "hit_rate": 0.82,
        "avg_return": 8.24,
        "conviction": 85,
        "gate": "PASSED"
      }
    ]
  },
  "overall": {
    "decision": "EXECUTE",
    "execute_count": 2,
    "wait_count": 3,
    "position_note": null
  }
}
```

### Flow Diagram

```
mock_server.py (or live API)
       |
       v
  [Stage 1: Watchdog]
  get_health() + get_signal_scores() + get_regime_state()
       |
       |---> STOP?  --> exit 2, print reason
       |---> DEGRADED? --> set caution_flag=true, continue
       |---> VALID? --> continue
       |
       v
  [Stage 2: Regime Scanner]
  get_filtered_signals() + get_signal_scores()
       |
       |---> 7-gate evaluation per signal
       |---> collect EXECUTE/WAIT decisions
       |
       v
  [Stage 3: Trade Decision]
  combine watchdog verdict + scanner decisions
       |
       |---> print human-readable report
       |---> write pipeline_output.json
       |---> exit 0 (EXECUTE), 1 (DEGRADED), 2 (STOP)
```

---

## 2. Dependencies and Setup

### Runtime Requirements

- **Python**: 3.10+
- **External packages**: none (stdlib only)
- **SDK**: `pf_regime_sdk/` (included in repo, imported via relative path)

### Environment Variables

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `PF_API_URL` | no | `http://localhost:8080` | API endpoint (live node or mock server) |

the script also accepts `--url http://host:port` as a CLI arg, which overrides the env var.

### No-Install Setup (Mock Mode)

builders dont need access to a live API node. the repo includes `examples/mock_server.py` which serves realistic responses for all 6 endpoints on localhost:8080. this is the default path for first-time users.

```
# terminal 1: start mock
python3 examples/mock_server.py

# terminal 2: run pipeline
python3 examples/full_pipeline_demo.py
```

### Live API Setup

```
export PF_API_URL=http://84.32.34.46:8080
python3 examples/full_pipeline_demo.py
```

### File Layout (After Implementation)

```
post-fiat-signals/
  examples/
    mock_server.py          # existing — serves all 6 endpoints locally
    watchdog.py             # existing — circuit breaker (standalone)
    regime_scanner.py       # existing — decision engine (standalone)
    full_pipeline_demo.py   # NEW — chains watchdog -> scanner -> trade decision
  pf_regime_sdk/
    client.py               # SDK client (6 methods, retry, backoff)
    models.py               # typed dataclasses for API responses
    exceptions.py           # error types
```

---

## 3. Inputs and Outputs

### Inputs

**Data sources** (all via SDK `RegimeClient`):

| SDK Method | API Endpoint | Used By | Returns |
|------------|-------------|---------|---------|
| `get_health()` | `/health` | Watchdog stage | API status, data age, staleness |
| `get_signal_scores()` | `/signals/reliability` | Watchdog + Scanner | per-type decay status, drop %, regime alert |
| `get_regime_state()` | `/regime/current` | Watchdog stage | regime classification, confidence, backtest context |
| `get_filtered_signals()` | `/signals/filtered` | Scanner stage | regime-gated signals with hit rates and filter classifications |

**Input format**: all inputs are JSON responses from the API, deserialized into typed dataclasses by the SDK. the demo script makes no direct HTTP calls — everything goes through `RegimeClient`.

**No file inputs**: the script doesnt read any local files. all data comes from the API (live or mock).

### Outputs

**1. Human-readable CLI report** (stdout)

structured report showing:
- watchdog verdict per dimension (system health, signal fidelity, regime confidence)
- scanner decisions per signal (pair, type, decision, gate, reason)
- overall trade decision with position sizing note if degraded

**2. Machine-readable JSON** (`pipeline_output.json`)

written to current working directory. schema shown in section 1 above. designed for downstream consumption — a builder can parse this to feed their own trading bot, alerting system, or dashboard.

**3. Exit codes**

| Code | Meaning | When |
|------|---------|------|
| 0 | EXECUTE — at least one signal passed all gates | watchdog VALID + scanner has EXECUTE |
| 1 | DEGRADED — signals present but conditions uncertain | watchdog DEGRADED, or zero EXECUTE signals |
| 2 | STOP — do not trade | watchdog STOP, or API unreachable |

exit codes are shell-chainable: `full_pipeline_demo.py && my_trading_bot.py` will only run the bot if the pipeline returns 0.

---

## 4. Quickstart

### for builders who want to see it work (2 minutes)

```bash
# clone the repo
git clone https://github.com/sendonanawitakeshi/post-fiat-signals.git
cd post-fiat-signals

# start the mock API (terminal 1)
python3 examples/mock_server.py &

# run the full pipeline (terminal 2)
python3 examples/full_pipeline_demo.py

# check the machine-readable output
cat pipeline_output.json | python3 -m json.tool
```

the mock server returns a NEUTRAL regime with 2 CRYPTO_LEADS signals (ACTIONABLE) and 2 SEMI_LEADS signals (SUPPRESS). expected output: 2 EXECUTE, 3 WAIT, overall EXECUTE.

### for builders who want to integrate it

the demo script is designed to be read, copied, and modified. key extension points:

**change decision thresholds**:
```python
# in the script header
ACTIONABLE_REGIME = "NEUTRAL"    # only trade during NEUTRAL
MIN_HIT_RATE = 0.65              # floor for hit rate gate
```

**add custom post-decision logic**:
```python
# after the pipeline runs
output = run_pipeline(api_url)

if output["overall"]["decision"] == "EXECUTE":
    for d in output["scanner"]["decisions"]:
        if d["decision"] == "EXECUTE":
            # your logic here: send order, log signal, alert webhook
            place_order(d["pair"], size=calculate_size(d))
```

**swap data source**:
```python
# point to your own API node instead of mock
export PF_API_URL=http://your-node:8080
python3 examples/full_pipeline_demo.py
```

**use exit codes in cron/automation**:
```bash
# run every 15 min, only execute bot if pipeline says go
*/15 * * * * cd /path/to/post-fiat-signals && python3 examples/full_pipeline_demo.py && python3 my_bot.py
```

### for builders who want to understand the logic

read the source files in this order:
1. `pf_regime_sdk/models.py` — what the API returns (typed dataclasses)
2. `pf_regime_sdk/client.py` — how the SDK talks to the API (retry, backoff, error handling)
3. `examples/watchdog.py` — how safety checks work (3 dimensions, thresholds)
4. `examples/regime_scanner.py` — how trade decisions work (7-gate filter)
5. `examples/full_pipeline_demo.py` — how it all chains together

---

## 5. Design Constraints

- **single file**: the demo must be one file (`full_pipeline_demo.py`), not a package. builders should be able to read it top to bottom.
- **zero deps**: stdlib + SDK only. no pip install required.
- **mock-first**: default behavior works against `mock_server.py` on localhost:8080. no live API required for first run.
- **reuse, dont duplicate**: import the SDK client. dont re-implement HTTP calls or data parsing.
- **exit codes matter**: downstream scripts chain on exit codes. 0/1/2 must be consistent and documented.
- **output is both human and machine**: print a readable report AND write structured JSON. different consumers need different formats.
- **no secrets**: the script must not contain API keys, wallet addresses, or server IPs. API URL comes from env var or CLI arg.

---

## 6. Implementation Scope

**what to build**:
- `examples/full_pipeline_demo.py` (~150-200 lines)
- chains watchdog checks → scanner evaluation → trade decision summary
- prints CLI report, writes `pipeline_output.json`
- returns exit code 0/1/2

**what NOT to build**:
- no new SDK methods — use existing `RegimeClient` as-is
- no modifications to `watchdog.py` or `regime_scanner.py` — those remain standalone
- no new API endpoints — demo consumes existing 6 endpoints
- no trading execution — the demo produces a decision, not an order

---

**Source wallet**: `rfLJ4ZRnqmGFLAcMvCD56nKGbjpdTJmMqo`
**SDK**: https://github.com/sendonanawitakeshi/post-fiat-signals
**Schema**: v1.1.0

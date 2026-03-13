# Builder Validation Report — First-Use Pipeline Test

**Date**: 2026-03-13
**Validator**: `rfLJ4ZRnqmGFLAcMvCD56nKGbjpdTJmMqo`
**Method**: Internal self-validation (fresh clone, followed only published [QUICKSTART.md](QUICKSTART.md))
**External outreach**: Follow-up sent to 2 builders ([hit0ri1](https://github.com/hit0ri1/PFT-Hive-Mind-Multi-Agent-Coordination-Logic/issues/1#issuecomment-4058066120), [prometheus88](https://github.com/prometheus88/Custom-Crypto-Indicator/issues/1#issuecomment-4058066327)) — responses pending

---

## Methodology

The published [QUICKSTART.md](QUICKSTART.md) was tested as a first-time builder would experience it: fresh `git clone` to a clean `/tmp/builder-test` directory, following only the 5 numbered steps in the quickstart with zero private instructions or supplementary context. The goal was to identify every point where a builder would pause, get confused, or fail.

Two external builders (hit0ri1 and prometheus88) were contacted via GitHub issue comments with the quickstart link and asked to attempt the same path independently. Neither has responded as of this report. This document will be updated when external feedback arrives.

---

## Outcome

**Status**: Successful first use (with one critical friction point, now fixed)

**Time to first output**: Under 5 seconds (excluding clone). The "under 5 minutes" claim in QUICKSTART.md is accurate and conservative.

**Python version tested**: 3.12.3 (prerequisite: 3.10+)

**All 33 tests pass** on fresh clone (`python3 -m unittest discover tests/ -v`).

---

## Friction Points Found

### P0 — Mock server silently crashes on port collision (FIXED)

**What happened**: The live signal API was already running on port 8080. When following QUICKSTART.md Step 2 (`python3 examples/mock_server.py &`), the mock server crashed with a raw `OSError: [Errno 98] Address already in use` traceback. Because `&` backgrounds the process, the traceback went to stderr and was easy to miss. The builder then unknowingly ran the pipeline against the live API instead of the mock, getting completely different output (NO_TRADE/STOP instead of EXECUTE_REDUCED).

**Impact**: Any builder on a machine where port 8080 is occupied would get output that doesnt match the quickstart, conclude the docs are wrong, and lose trust.

**Fix shipped**: `examples/mock_server.py` now catches `OSError` errno 98 and prints a clear message:

```
Error: port 8080 is already in use.
Try a different port:  python3 examples/mock_server.py --port 9090
Then set:              export PF_API_URL=http://localhost:9090
```

**Commit**: included in this report's commit.

### P1 — Mock backtestContext values used wrong scale (FIXED)

**What happened**: The mock returned `"accuracy": 0.60` and `"fpRate": 0.40` (decimal 0-1 scale). The live API returns `60` and `40` (percentage scale). The watchdog formats these as percentages, producing `1%` and `0%` against the mock — obviously wrong numbers that undermine confidence.

**Fix shipped**: Changed mock values to `60` and `40` to match live API scale.

### P2 — Mock regimeAlert field names didnt match live API (FIXED)

**What happened**: The mock used `{"active": false, "decayingTypes": 1, "threshold": 2}` for regimeAlert. The live API uses `{"triggered": true, "count": 3, "types": [...], "msg": "..."}`. The watchdog checks `alert.get("triggered")` which returned `None` against the mock — happened to produce correct behavior by accident, but was a latent inconsistency.

**Fix shipped**: Mock now uses live API field names (`triggered`, `count`, `types`, `msg`).

### P3 — README sample size discrepancy (FIXED)

**What happened**: README said `n=17` for NEUTRAL+CRYPTO_LEADS, while QUICKSTART.md, the mock, and the regime filter source all use `n=22`. The README value was stale.

**Fix shipped**: README updated to `n=22`.

---

## What Works Well

- **Zero-dependency claim is real.** Clone, run, done. No pip, no venv, no API keys, no internet (mock path).
- **Error message when API is unreachable** is clear and actionable: tells you the error, suggests starting the mock, shows the command.
- **Exit codes work correctly** for shell chaining (`&&`).
- **JSON output** (`pipeline_output.json`) is clean, complete, and machine-readable.
- **QUICKSTART expected output** matches actual output exactly (minus ANSI color codes and timestamp).
- **Stage annotations** in QUICKSTART.md add genuine value — the tables explaining watchdog dimensions and 7-gate logic give enough context to understand the output without reading the full docs.
- **STOP diagnostic is discoverable**: clearly linked from QUICKSTART.md "When the Live API Returns STOP" section.

---

## Improvements Shipped From This Validation

| # | Issue | Fix | Status |
|---|-------|-----|--------|
| 1 | Mock crashes silently on port collision | `mock_server.py`: catch OSError, print actionable message | **Shipped** |
| 2 | backtestContext accuracy/fpRate wrong scale | `mock_server.py`: changed 0.60/0.40 to 60/40 | **Shipped** |
| 3 | regimeAlert field names inconsistent | `mock_server.py`: aligned to live API schema | **Shipped** |
| 4 | README n=17 stale value | `README.md`: updated to n=22 | **Shipped** |

All 4 fixes verified — 33/33 tests pass after changes.

---

## External Builder Outreach Status

| Builder | Repo | Issue | Quickstart sent | Response |
|---------|------|-------|-----------------|----------|
| hit0ri1 | PFT-Hive-Mind-Multi-Agent-Coordination-Logic | [#1](https://github.com/hit0ri1/PFT-Hive-Mind-Multi-Agent-Coordination-Logic/issues/1) | 2026-03-13 | Pending |
| prometheus88 | Custom-Crypto-Indicator | [#1](https://github.com/prometheus88/Custom-Crypto-Indicator/issues/1) | 2026-03-13 | Pending |

Both received a follow-up comment linking directly to QUICKSTART.md with a request to attempt the clone-to-output path and report friction. This report will be updated when responses arrive.

---

## References

- **Quickstart guide**: [QUICKSTART.md](QUICKSTART.md)
- **System health surface**: [status.json](status.json) | [Live endpoint](http://84.32.34.46:8080/system/status)
- **STOP state diagnostic**: [docs/STOP_STATE_DIAGNOSTIC.md](docs/STOP_STATE_DIAGNOSTIC.md)
- **Integration tests**: [TESTING.md](TESTING.md) — 15 tests across HEALTHY/DEGRADED/HALT paths
- **Public repo**: [github.com/sendonanawitakeshi/post-fiat-signals](https://github.com/sendonanawitakeshi/post-fiat-signals)

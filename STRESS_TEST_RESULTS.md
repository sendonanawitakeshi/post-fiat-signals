# PF-Regime-SDK Stress Test Results

**Version**: 0.3.0
**Date**: 2026-03-09
**Runtime**: 2.5s (18 tests, 1 retry each, 0s backoff)
**Result**: 18/18 PASS

## Test Infrastructure

- Mock HTTP server: `http.server.ThreadingHTTPServer` on `localhost:19876`
- Zero external dependencies (stdlib only)
- 8 mock response modes: valid_json, malformed_json, empty_body, partial_json, http_500, http_502, http_503, slow_response
- Connection-refused tests use an ephemeral port with no listener

## Failure Mode Reference

### Group A: Transport Layer (`_request()`)

| # | Scenario | Server Response | SDK Exception | Verified |
|---|----------|----------------|---------------|----------|
| A1 | Valid 200 | Well-formed JSON | Returns `RegimeState` | PASS |
| A2 | Malformed JSON | `{"broken": true, "missing_close` | `RetryExhaustedError(last_error=RegimeAPIError)` | PASS |
| A3 | Empty body | 200 + zero-length body | `RetryExhaustedError(last_error=RegimeAPIError)` | PASS |
| A4 | HTTP 500 | 500 Internal Server Error | `RetryExhaustedError(last_error=RegimeAPIError, status_code=500)` | PASS |
| A5 | HTTP 502 | 502 Bad Gateway | `RetryExhaustedError(last_error=RegimeAPIError, status_code=502)` | PASS |
| A6 | HTTP 503 | 503 Service Unavailable | `RetryExhaustedError(last_error=WarmingError)` | PASS |
| A7 | Connection refused | No listener on port | `RetryExhaustedError(last_error=ConnectionError)` | PASS |
| A8 | Timeout | 5s delay, 1s client timeout | `RetryExhaustedError(last_error=TimeoutError)` | PASS |
| A9 | Stale data | `isStale: true, dataAgeSec: 9999` | `StaleDataError(data_age_sec=9999)` | PASS |

### Group B: Model Deserialization

| # | Scenario | Input | SDK Behavior | Verified |
|---|----------|-------|-------------|----------|
| B1 | Partial regime | `{"randomField": true}` (missing `state`, `confidence`) | `RegimeAPIError("Unexpected response format...")` — NOT raw `KeyError` | PASS |
| B2 | Partial health | `{"status": "ok"}` only | `HealthStatus` with defaults (uptime=0, schema_version="") | PASS |
| B3 | Partial filtered | `{"regimeId": "SYSTEMIC"}` only | `FilteredSignalReport` with defaults (signals=[], counts=0) | PASS |
| B4 | Partial reliability | `{"window": 30}` only | `ReliabilityReport` with defaults (types={}) | PASS |
| B5 | Partial rebalance | `{"regimeState": "NEUTRAL"}` only | `RebalanceQueue` with defaults (trades=[]) | PASS |

### Group C: `get_health()` Endpoint

| # | Scenario | Server Response | SDK Exception | Verified |
|---|----------|----------------|---------------|----------|
| C1 | Valid health | Well-formed JSON | Returns `HealthStatus` | PASS |
| C2 | Health timeout | 5s delay, 1s timeout | `TimeoutError` (not generic `ConnectionError`) | PASS |
| C3 | Health malformed JSON | Truncated JSON string | `RegimeAPIError` (not generic `ConnectionError`) | PASS |
| C4 | Health connection refused | No listener on port | `ConnectionError` | PASS |

## SDK Patches Applied (v0.2.0 -> v0.3.0)

### Patch 1: `OSError` catch in `_request()`
Previously, `socket.timeout` during response read bubbled up as raw `OSError`. Now caught and mapped to `TimeoutError` (if "timed out" in message) or `ConnectionError` (otherwise).

### Patch 2: `from_dict()` KeyError wrapping
All 6 public methods (`get_regime_state`, `get_rebalance_queue`, `get_signal_scores`, `get_filtered_signals`, `get_regime_history`, `get_health`) now catch `KeyError`/`TypeError` from `from_dict()` and raise `RegimeAPIError` with a descriptive message. Consumers never see raw Python exceptions.

### Patch 3: Granular `get_health()` errors
Previously, `get_health()` caught `(URLError, JSONDecodeError)` and raised generic `ConnectionError` for everything. Now:
- URLError with "timed out" -> `TimeoutError`
- URLError otherwise -> `ConnectionError`
- JSONDecodeError -> `RegimeAPIError`
- OSError with "timed out" -> `TimeoutError`
- OSError otherwise -> `ConnectionError`
- KeyError/TypeError from `from_dict()` -> `RegimeAPIError`

## Consumer Reliability Contract

If you are integrating this SDK, here is what you can rely on:

1. **All transport failures retry** (configurable via `max_retries`, default 3) with exponential backoff
2. **After retries exhaust**, you always get `RetryExhaustedError` with `.last_error` containing the specific failure type
3. **`get_health()` does NOT retry** — single attempt, specific exception types
4. **You will never see raw `KeyError`, `OSError`, or `socket.timeout`** from any public method
5. **Exception hierarchy**: `RegimeAPIError` is the base. `ConnectionError`, `TimeoutError`, `WarmingError`, `StaleDataError`, `RetryExhaustedError` all inherit from it. A single `except RegimeAPIError` catches everything.

## Raw Test Output

```
Ran 18 tests in 2.539s — OK

  [PASS] A1: valid_200 -> RegimeState(NEUTRAL, 72)
  [PASS] A2: malformed_json -> RetryExhaustedError(RegimeAPIError)
  [PASS] A3: empty_body -> RetryExhaustedError(RegimeAPIError)
  [PASS] A4: http_500 -> RetryExhaustedError(status=500)
  [PASS] A5: http_502 -> RetryExhaustedError(status=502)
  [PASS] A6: http_503 -> RetryExhaustedError(WarmingError)
  [PASS] A7: connection_refused -> RetryExhaustedError(ConnectionError)
  [PASS] A8: timeout -> RetryExhaustedError(TimeoutError)
  [PASS] A9: stale_data -> StaleDataError(age=9999)
  [PASS] B1: partial_regime -> RegimeAPIError (not KeyError)
  [PASS] B2: partial_health -> HealthStatus(defaults)
  [PASS] B3: partial_filtered -> FilteredSignalReport(defaults)
  [PASS] B4: partial_reliability -> ReliabilityReport(empty types)
  [PASS] B5: partial_rebalance -> RebalanceQueue(empty trades)
  [PASS] C1: health_valid -> HealthStatus(ok)
  [PASS] C2: health_timeout -> TimeoutError
  [PASS] C3: health_malformed -> RegimeAPIError (not ConnectionError)
  [PASS] C4: health_refused -> ConnectionError
```

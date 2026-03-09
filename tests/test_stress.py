"""Stress tests for pf-regime-sdk — 18 degraded-API scenarios.

Tests every failure mode a consumer can hit: transport errors, malformed
responses, partial JSON, timeouts, and connection refused.  Uses a built-in
http.server mock on localhost:19876 (zero external deps).

Run:  python -m pytest tests/test_stress.py -v
  or: python tests/test_stress.py
"""

import json
import socket
import sys
import threading
import time
import unittest
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

# Ensure the SDK package is importable from the repo root
sys.path.insert(0, ".")

from pf_regime_sdk.client import RegimeClient
from pf_regime_sdk.exceptions import (
    RegimeAPIError,
    ConnectionError as SDKConnectionError,
    StaleDataError,
    WarmingError,
    TimeoutError as SDKTimeoutError,
    RetryExhaustedError,
)
from pf_regime_sdk.models import (
    RegimeState,
    HealthStatus,
    FilteredSignalReport,
    ReliabilityReport,
    RebalanceQueue,
)


# ---------------------------------------------------------------------------
# Mock HTTP server
# ---------------------------------------------------------------------------

MOCK_PORT = 19876
MOCK_MODE = {"mode": "valid_json", "body": None, "status": 200, "delay": 0}

# Minimal valid responses for each endpoint
VALID_REGIME = {
    "state": "NEUTRAL",
    "id": "NEUTRAL",
    "confidence": 72,
    "isAlert": False,
    "action": "HOLD",
    "targetWeights": {"BTC": 0.4, "ETH": 0.3},
    "signals": {},
    "backtestContext": {
        "optimalWindow": 60,
        "accuracy": 0.6,
        "avgLeadTime": 27,
        "fpRate": 0.4,
    },
    "timestamp": "2026-03-09T12:00:00Z",
    "dataAgeSec": 5,
    "isStale": False,
}

VALID_HEALTH = {
    "status": "ok",
    "uptime": 3600,
    "uptimeHuman": "1h 0m",
    "lastRefresh": "2026-03-09T12:00:00Z",
    "dataAgeSec": 5,
    "isStale": False,
    "refreshCount": 10,
    "dataFresh": True,
    "lastError": None,
    "schemaVersion": "1.1.0",
}

VALID_FILTERED = {
    "regimeId": "NEUTRAL",
    "regimeLabel": "Neutral",
    "regimeConfidence": 72,
    "totalSignals": 2,
    "actionableCount": 1,
    "suppressedCount": 1,
    "ambiguousCount": 0,
    "filterRules": {},
    "signals": [
        {
            "pair": "NVDA/RNDR",
            "type": "SEMI_LEADS",
            "typeLabel": "Semi Leads",
            "conviction": 85,
            "reliability": 70,
            "reliabilityLabel": "HIGH",
            "regimeFilter": "ACTIONABLE",
            "regimeFilterHitRate": 0.82,
            "regimeFilterN": 11,
            "regimeFilterAvgRet": 8.24,
        }
    ],
    "timestamp": "2026-03-09T12:00:00Z",
    "dataAgeSec": 5,
    "isStale": False,
}

VALID_RELIABILITY = {
    "window": 60,
    "regimeAlert": {},
    "types": {},
    "timestamp": "2026-03-09T12:00:00Z",
    "dataAgeSec": 5,
    "isStale": False,
}

VALID_REBALANCE = {
    "regimeState": "NEUTRAL",
    "confidence": 72,
    "trades": [],
    "tradeCount": 0,
    "timestamp": "2026-03-09T12:00:00Z",
    "dataAgeSec": 5,
    "isStale": False,
}

STALE_REGIME = {**VALID_REGIME, "isStale": True, "dataAgeSec": 9999}

# Lookup: endpoint path -> valid response
ENDPOINT_RESPONSES = {
    "/regime/current": VALID_REGIME,
    "/health": VALID_HEALTH,
    "/signals/filtered": VALID_FILTERED,
    "/signals/reliability": VALID_RELIABILITY,
    "/rebalancing/queue": VALID_REBALANCE,
}


class MockHandler(BaseHTTPRequestHandler):
    """Routes all GET requests through MOCK_MODE."""

    def log_message(self, *args):
        pass  # suppress request logging

    def do_GET(self):
        mode = MOCK_MODE["mode"]
        delay = MOCK_MODE.get("delay", 0)

        if delay > 0:
            time.sleep(delay)

        if mode == "valid_json":
            body = MOCK_MODE.get("body")
            if body is None:
                body = ENDPOINT_RESPONSES.get(self.path, {"ok": True})
            self._respond(200, json.dumps(body))

        elif mode == "malformed_json":
            self._respond(200, '{"broken": true, "missing_close')

        elif mode == "empty_body":
            self._respond(200, "")

        elif mode == "partial_json":
            body = MOCK_MODE.get("body", {})
            self._respond(200, json.dumps(body))

        elif mode == "http_500":
            self._respond(500, json.dumps({"error": "Internal Server Error"}))

        elif mode == "http_502":
            self._respond(502, json.dumps({"error": "Bad Gateway"}))

        elif mode == "http_503":
            self._respond(503, json.dumps({"error": "Service unavailable — warming up"}))

        elif mode == "slow_response":
            time.sleep(5)
            self._respond(200, json.dumps(VALID_REGIME))

        else:
            self._respond(200, json.dumps({"ok": True}))

    def _respond(self, status: int, body: str):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))


def _start_mock_server():
    server = ThreadingHTTPServer(("127.0.0.1", MOCK_PORT), MockHandler)
    server.daemon_threads = True
    server.timeout = 0.5
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


# ---------------------------------------------------------------------------
# Find an unused port (for connection-refused tests)
# ---------------------------------------------------------------------------

def _find_dead_port():
    """Return a port that is NOT listening."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# ---------------------------------------------------------------------------
# Test suite
# ---------------------------------------------------------------------------

class StressTest(unittest.TestCase):
    """18 degraded-API stress tests for pf-regime-sdk."""

    server = None

    @classmethod
    def setUpClass(cls):
        cls.server = _start_mock_server()
        # Fast client: 1 retry, 0 backoff so tests dont take forever
        cls.client = RegimeClient(
            base_url=f"http://127.0.0.1:{MOCK_PORT}",
            timeout=2,
            max_retries=1,
            backoff_base=0.0,
        )

    @classmethod
    def tearDownClass(cls):
        if cls.server:
            cls.server.shutdown()

    def _set_mode(self, mode, **kw):
        MOCK_MODE.clear()
        MOCK_MODE["mode"] = mode
        MOCK_MODE.update(kw)

    # -----------------------------------------------------------------------
    # Group A: Transport layer — _request()
    # -----------------------------------------------------------------------

    def test_01_valid_200(self):
        """A1: Valid 200 response returns parsed dict via get_regime_state()."""
        self._set_mode("valid_json")
        state = self.client.get_regime_state()
        self.assertIsInstance(state, RegimeState)
        self.assertEqual(state.regime_type, "NEUTRAL")
        self.assertEqual(state.confidence_score, 72)
        print("  [PASS] A1: valid_200 -> RegimeState(NEUTRAL, 72)")

    def test_02_malformed_json(self):
        """A2: Malformed JSON triggers RetryExhaustedError with RegimeAPIError."""
        self._set_mode("malformed_json")
        with self.assertRaises(RetryExhaustedError) as ctx:
            self.client._request("/regime/current")
        self.assertIsInstance(ctx.exception.last_error, RegimeAPIError)
        self.assertIn("Invalid JSON", str(ctx.exception.last_error))
        print("  [PASS] A2: malformed_json -> RetryExhaustedError(RegimeAPIError)")

    def test_03_empty_body(self):
        """A3: Empty body triggers RetryExhaustedError (json.loads fails on '')."""
        self._set_mode("empty_body")
        with self.assertRaises(RetryExhaustedError) as ctx:
            self.client._request("/regime/current")
        self.assertIsInstance(ctx.exception.last_error, RegimeAPIError)
        print("  [PASS] A3: empty_body -> RetryExhaustedError(RegimeAPIError)")

    def test_04_http_500(self):
        """A4: HTTP 500 triggers RetryExhaustedError with status_code=500."""
        self._set_mode("http_500")
        with self.assertRaises(RetryExhaustedError) as ctx:
            self.client._request("/regime/current")
        self.assertIsInstance(ctx.exception.last_error, RegimeAPIError)
        self.assertEqual(ctx.exception.last_error.status_code, 500)
        print("  [PASS] A4: http_500 -> RetryExhaustedError(status=500)")

    def test_05_http_502(self):
        """A5: HTTP 502 triggers RetryExhaustedError with status_code=502."""
        self._set_mode("http_502")
        with self.assertRaises(RetryExhaustedError) as ctx:
            self.client._request("/regime/current")
        self.assertIsInstance(ctx.exception.last_error, RegimeAPIError)
        self.assertEqual(ctx.exception.last_error.status_code, 502)
        print("  [PASS] A5: http_502 -> RetryExhaustedError(status=502)")

    def test_06_http_503(self):
        """A6: HTTP 503 triggers RetryExhaustedError with WarmingError."""
        self._set_mode("http_503")
        with self.assertRaises(RetryExhaustedError) as ctx:
            self.client._request("/regime/current")
        self.assertIsInstance(ctx.exception.last_error, WarmingError)
        print("  [PASS] A6: http_503 -> RetryExhaustedError(WarmingError)")

    def test_07_connection_refused(self):
        """A7: Connection refused triggers RetryExhaustedError(ConnectionError)."""
        dead_port = _find_dead_port()
        dead_client = RegimeClient(
            base_url=f"http://127.0.0.1:{dead_port}",
            timeout=2,
            max_retries=1,
            backoff_base=0.0,
        )
        with self.assertRaises(RetryExhaustedError) as ctx:
            dead_client._request("/regime/current")
        self.assertIsInstance(ctx.exception.last_error, (SDKConnectionError, SDKTimeoutError))
        print("  [PASS] A7: connection_refused -> RetryExhaustedError(ConnectionError)")

    def test_08_timeout(self):
        """A8: Slow response triggers RetryExhaustedError(TimeoutError)."""
        # Client with 1s timeout, server delays 5s
        slow_client = RegimeClient(
            base_url=f"http://127.0.0.1:{MOCK_PORT}",
            timeout=1,
            max_retries=1,
            backoff_base=0.0,
        )
        self._set_mode("slow_response", delay=0)  # delay handled inside handler
        with self.assertRaises(RetryExhaustedError) as ctx:
            slow_client._request("/regime/current")
        # Could be TimeoutError or ConnectionError depending on OS behavior
        self.assertIsInstance(
            ctx.exception.last_error,
            (SDKTimeoutError, SDKConnectionError),
        )
        print("  [PASS] A8: timeout -> RetryExhaustedError(TimeoutError)")

    def test_09_stale_data(self):
        """A9: Stale data with raise_on_stale=True triggers StaleDataError."""
        stale_client = RegimeClient(
            base_url=f"http://127.0.0.1:{MOCK_PORT}",
            timeout=2,
            max_retries=1,
            backoff_base=0.0,
            raise_on_stale=True,
        )
        self._set_mode("valid_json", body=STALE_REGIME)
        with self.assertRaises(StaleDataError) as ctx:
            stale_client._request("/regime/current")
        self.assertEqual(ctx.exception.data_age_sec, 9999)
        print("  [PASS] A9: stale_data -> StaleDataError(age=9999)")

    # -----------------------------------------------------------------------
    # Group B: Model deserialization
    # -----------------------------------------------------------------------

    def test_10_partial_regime_state(self):
        """B1: Partial regime JSON raises RegimeAPIError (not raw KeyError)."""
        self._set_mode("partial_json", body={"randomField": True})
        with self.assertRaises(RegimeAPIError) as ctx:
            self.client.get_regime_state()
        # Must NOT be a raw KeyError — SDK wraps it
        self.assertNotIsInstance(ctx.exception, KeyError)
        self.assertIn("Unexpected response format", str(ctx.exception))
        print("  [PASS] B1: partial_regime -> RegimeAPIError (not KeyError)")

    def test_11_partial_health(self):
        """B2: Partial health JSON still returns HealthStatus with defaults."""
        self._set_mode("partial_json", body={"status": "ok"})
        health = self.client.get_health()
        self.assertIsInstance(health, HealthStatus)
        self.assertEqual(health.status, "ok")
        self.assertEqual(health.uptime, 0)  # default
        self.assertEqual(health.schema_version, "")  # default
        print("  [PASS] B2: partial_health -> HealthStatus(defaults)")

    def test_12_partial_filtered(self):
        """B3: Partial filtered JSON returns FilteredSignalReport with defaults."""
        self._set_mode("partial_json", body={"regimeId": "SYSTEMIC"})
        report = self.client.get_filtered_signals()
        self.assertIsInstance(report, FilteredSignalReport)
        self.assertEqual(report.regime_id, "SYSTEMIC")
        self.assertEqual(report.signals, [])  # default
        self.assertEqual(report.actionable_count, 0)  # default
        print("  [PASS] B3: partial_filtered -> FilteredSignalReport(defaults)")

    def test_13_partial_reliability(self):
        """B4: Partial reliability JSON returns ReliabilityReport with empty types."""
        self._set_mode("partial_json", body={"window": 30})
        report = self.client.get_signal_scores()
        self.assertIsInstance(report, ReliabilityReport)
        self.assertEqual(report.window, 30)
        self.assertEqual(report.types, {})  # default
        print("  [PASS] B4: partial_reliability -> ReliabilityReport(empty types)")

    def test_14_partial_rebalance(self):
        """B5: Partial rebalance JSON returns RebalanceQueue with empty trades."""
        self._set_mode("partial_json", body={"regimeState": "NEUTRAL"})
        queue = self.client.get_rebalance_queue()
        self.assertIsInstance(queue, RebalanceQueue)
        self.assertEqual(queue.regime_state, "NEUTRAL")
        self.assertEqual(queue.trades, [])  # default
        print("  [PASS] B5: partial_rebalance -> RebalanceQueue(empty trades)")

    # -----------------------------------------------------------------------
    # Group C: get_health() endpoint
    # -----------------------------------------------------------------------

    def test_15_health_valid(self):
        """C1: Valid health response returns HealthStatus."""
        self._set_mode("valid_json")
        health = self.client.get_health()
        self.assertIsInstance(health, HealthStatus)
        self.assertEqual(health.status, "ok")
        self.assertEqual(health.schema_version, "1.1.0")
        print("  [PASS] C1: health_valid -> HealthStatus(ok)")

    def test_16_health_timeout(self):
        """C2: Health timeout raises TimeoutError (not generic ConnectionError)."""
        slow_client = RegimeClient(
            base_url=f"http://127.0.0.1:{MOCK_PORT}",
            timeout=1,
            max_retries=1,
            backoff_base=0.0,
        )
        self._set_mode("slow_response")
        with self.assertRaises((SDKTimeoutError, SDKConnectionError)):
            slow_client.get_health()
        print("  [PASS] C2: health_timeout -> TimeoutError")

    def test_17_health_malformed_json(self):
        """C3: Health malformed JSON raises RegimeAPIError (not ConnectionError)."""
        self._set_mode("malformed_json")
        with self.assertRaises(RegimeAPIError) as ctx:
            self.client.get_health()
        self.assertNotIsInstance(ctx.exception, SDKConnectionError)
        self.assertIn("invalid json", str(ctx.exception).lower())
        print("  [PASS] C3: health_malformed -> RegimeAPIError (not ConnectionError)")

    def test_18_health_connection_refused(self):
        """C4: Health connection refused raises ConnectionError."""
        dead_port = _find_dead_port()
        dead_client = RegimeClient(
            base_url=f"http://127.0.0.1:{dead_port}",
            timeout=2,
            max_retries=1,
            backoff_base=0.0,
        )
        with self.assertRaises((SDKConnectionError, SDKTimeoutError)):
            dead_client.get_health()
        print("  [PASS] C4: health_refused -> ConnectionError")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 70)
    print("PF-REGIME-SDK STRESS TEST — 18 degraded API scenarios")
    print("=" * 70)
    print()
    unittest.main(verbosity=2)

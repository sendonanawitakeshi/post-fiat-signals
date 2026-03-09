"""HTTP client for the Post Fiat Regime-Aware Signal Intelligence API."""

import json
import logging
import time
import urllib.request
import urllib.error
from typing import Optional

from .models import (
    RegimeState,
    RebalanceQueue,
    ReliabilityReport,
    RegimeHistory,
    HealthStatus,
    FilteredSignalReport,
)
from .exceptions import (
    RegimeAPIError,
    ConnectionError,
    StaleDataError,
    WarmingError,
    TimeoutError,
    RetryExhaustedError,
)

logger = logging.getLogger("pf_regime_sdk")


class RegimeClient:
    """Client for the Post Fiat Signal Intelligence API.

    Args:
        base_url: API base URL (default: http://localhost:8080)
        timeout: Request timeout in seconds (default: 10)
        max_retries: Maximum retry attempts on transient failures (default: 3)
        backoff_base: Base delay for exponential backoff in seconds (default: 1.0)
        raise_on_stale: If True, raise StaleDataError when isStale=true (default: False)
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        timeout: int = 10,
        max_retries: int = 3,
        backoff_base: float = 1.0,
        raise_on_stale: bool = False,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.raise_on_stale = raise_on_stale

    def _request(self, path: str) -> dict:
        """Make an HTTP GET request with retry and exponential backoff."""
        url = f"{self.base_url}{path}"
        last_error: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.debug(f"GET {url} (attempt {attempt}/{self.max_retries})")
                req = urllib.request.Request(url, headers={"Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    status = resp.status
                    body = resp.read().decode("utf-8")

                data = json.loads(body)

                if status == 503:
                    raise WarmingError(data.get("error", "Service unavailable"))

                if data.get("isStale"):
                    age = data.get("dataAgeSec", 0)
                    msg = f"Data is stale ({age}s old) from {path}"
                    logger.warning(msg)
                    if self.raise_on_stale:
                        raise StaleDataError(msg, data_age_sec=age)

                return data

            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8") if e.fp else ""
                try:
                    err_data = json.loads(body)
                except (json.JSONDecodeError, ValueError):
                    err_data = {}

                if e.code == 503:
                    last_error = WarmingError(err_data.get("error", "Service unavailable"))
                    logger.warning(f"API warming (503), retry {attempt}/{self.max_retries}")
                elif e.code >= 500:
                    last_error = RegimeAPIError(f"Server error {e.code}", status_code=e.code)
                    logger.warning(f"Server error {e.code}, retry {attempt}/{self.max_retries}")
                else:
                    raise RegimeAPIError(
                        err_data.get("error", f"HTTP {e.code}"),
                        status_code=e.code,
                    )

            except urllib.error.URLError as e:
                reason = str(e.reason) if hasattr(e, "reason") else str(e)
                if "timed out" in reason.lower():
                    last_error = TimeoutError(f"Request timed out after {self.timeout}s")
                    logger.warning(f"Timeout on {url}, retry {attempt}/{self.max_retries}")
                else:
                    last_error = ConnectionError(f"Connection failed: {reason}")
                    logger.warning(f"Connection failed: {reason}, retry {attempt}/{self.max_retries}")

            except json.JSONDecodeError as e:
                last_error = RegimeAPIError(f"Invalid JSON response: {e}")
                logger.warning(f"Bad JSON from {url}, retry {attempt}/{self.max_retries}")

            if attempt < self.max_retries:
                delay = self.backoff_base * (2 ** (attempt - 1))
                logger.info(f"Backing off {delay:.1f}s before retry")
                time.sleep(delay)

        raise RetryExhaustedError(
            f"All {self.max_retries} attempts failed for {path}",
            last_error=last_error,
        )

    def get_regime_state(self) -> RegimeState:
        """Fetch current regime classification."""
        data = self._request("/regime/current")
        return RegimeState.from_dict(data)

    def get_rebalance_queue(self) -> RebalanceQueue:
        """Fetch the active rebalancing queue."""
        data = self._request("/rebalancing/queue")
        return RebalanceQueue.from_dict(data)

    def get_signal_scores(self) -> ReliabilityReport:
        """Fetch signal reliability scores with decay status."""
        data = self._request("/signals/reliability")
        return ReliabilityReport.from_dict(data)

    def get_filtered_signals(self) -> FilteredSignalReport:
        """Fetch regime-conditional signal filter report."""
        data = self._request("/signals/filtered")
        return FilteredSignalReport.from_dict(data)

    def get_regime_history(self) -> RegimeHistory:
        """Fetch 90-day regime transition timeline."""
        data = self._request("/regime/history")
        return RegimeHistory.from_dict(data)

    def get_health(self) -> HealthStatus:
        """Fetch server health status. Does not retry — single attempt."""
        url = f"{self.base_url}/health"
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return HealthStatus.from_dict(data)
        except (urllib.error.URLError, json.JSONDecodeError) as e:
            raise ConnectionError(f"Health check failed: {e}")

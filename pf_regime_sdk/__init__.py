"""Post Fiat Regime SDK — Python client for the Signal Intelligence API."""

from .client import RegimeClient
from .models import (
    RegimeState,
    RebalanceEntry,
    RebalanceQueue,
    SignalReliability,
    ReliabilityReport,
    RegimeEvent,
    RegimeHistory,
    HealthStatus,
    SignalState,
    BacktestContext,
    FilterRule,
    FilteredSignal,
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

__version__ = "0.3.0"
__all__ = [
    "RegimeClient",
    "RegimeState",
    "RebalanceEntry",
    "RebalanceQueue",
    "SignalReliability",
    "ReliabilityReport",
    "RegimeEvent",
    "RegimeHistory",
    "HealthStatus",
    "SignalState",
    "BacktestContext",
    "FilterRule",
    "FilteredSignal",
    "FilteredSignalReport",
    "RegimeAPIError",
    "ConnectionError",
    "StaleDataError",
    "WarmingError",
    "TimeoutError",
    "RetryExhaustedError",
]

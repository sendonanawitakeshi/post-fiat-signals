"""Custom exceptions for the Post Fiat Regime SDK."""


class RegimeAPIError(Exception):
    """Base exception for all API errors."""

    def __init__(self, message: str, status_code: int | None = None):
        self.status_code = status_code
        super().__init__(message)


class ConnectionError(RegimeAPIError):
    """Raised when the API server is unreachable."""
    pass


class StaleDataError(RegimeAPIError):
    """Raised when API returns data flagged as stale (isStale: true)."""

    def __init__(self, message: str, data_age_sec: int):
        self.data_age_sec = data_age_sec
        super().__init__(message, status_code=200)


class WarmingError(RegimeAPIError):
    """Raised when API is still warming up (503, cache not loaded)."""

    def __init__(self, message: str = "API warming up — cache not loaded"):
        super().__init__(message, status_code=503)


class TimeoutError(RegimeAPIError):
    """Raised when a request exceeds the configured timeout."""
    pass


class RetryExhaustedError(RegimeAPIError):
    """Raised when all retry attempts have been exhausted."""

    def __init__(self, message: str, last_error: Exception | None = None):
        self.last_error = last_error
        super().__init__(message)

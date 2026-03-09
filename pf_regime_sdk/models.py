"""Typed data classes for Post Fiat Regime API responses."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SignalState:
    """Per-signal-type state within a regime classification."""
    label: str
    current_score: Optional[int]
    all_time_score: Optional[int]
    drop_pct: float
    decaying: bool

    @classmethod
    def from_dict(cls, d: dict) -> "SignalState":
        return cls(
            label=d["label"],
            current_score=d.get("currentScore"),
            all_time_score=d.get("allTimeScore"),
            drop_pct=d.get("dropPct", 0),
            decaying=d.get("decaying", False),
        )


@dataclass
class BacktestContext:
    """Backtest validation context for the current regime classification."""
    optimal_window: int
    accuracy: float
    avg_lead_time: float
    fp_rate: float

    @classmethod
    def from_dict(cls, d: dict) -> "BacktestContext":
        return cls(
            optimal_window=d["optimalWindow"],
            accuracy=d["accuracy"],
            avg_lead_time=d["avgLeadTime"],
            fp_rate=d["fpRate"],
        )


@dataclass
class RegimeState:
    """Current regime classification with confidence and signal breakdown."""
    regime_type: str
    regime_id: str
    confidence_score: int
    is_alert: bool
    action: str
    target_weights: dict[str, float]
    signals: dict[str, SignalState]
    backtest_context: Optional[BacktestContext]
    timestamp: str
    data_age_sec: Optional[int]
    is_stale: bool

    @classmethod
    def from_dict(cls, d: dict) -> "RegimeState":
        signals = {}
        for k, v in d.get("signals", {}).items():
            signals[k] = SignalState.from_dict(v)
        bt = d.get("backtestContext")
        return cls(
            regime_type=d["state"],
            regime_id=d.get("id", "NEUTRAL"),
            confidence_score=d["confidence"],
            is_alert=d.get("isAlert", False),
            action=d.get("action", ""),
            target_weights=d.get("targetWeights", {}),
            signals=signals,
            backtest_context=BacktestContext.from_dict(bt) if bt else None,
            timestamp=d.get("timestamp", ""),
            data_age_sec=d.get("dataAgeSec"),
            is_stale=d.get("isStale", False),
        )

    def __str__(self) -> str:
        decaying = [k for k, v in self.signals.items() if v.decaying]
        return (
            f"RegimeState(regime_type={self.regime_type!r}, "
            f"confidence_score={self.confidence_score}, "
            f"is_alert={self.is_alert}, "
            f"decaying_signals={decaying})"
        )


@dataclass
class RebalanceEntry:
    """A single trade instruction from the rebalancing queue."""
    asset: str
    direction: str
    current_pct: float
    target_pct: float
    delta_pct: float
    urgency: str
    urgency_label: str
    driving_signal: str
    regime: str

    @classmethod
    def from_dict(cls, d: dict) -> "RebalanceEntry":
        return cls(
            asset=d["asset"],
            direction=d["direction"],
            current_pct=d.get("currentPct", 0),
            target_pct=d.get("targetPct", 0),
            delta_pct=d.get("deltaPct", 0),
            urgency=d.get("urgency", "watch"),
            urgency_label=d.get("urgencyLabel", "Watch"),
            driving_signal=d.get("drivingSignal", ""),
            regime=d.get("regime", ""),
        )

    def __str__(self) -> str:
        sign = "+" if self.delta_pct > 0 else ""
        return (
            f"RebalanceEntry(asset={self.asset!r}, "
            f"direction={self.direction!r}, "
            f"delta={sign}{self.delta_pct}%, "
            f"urgency={self.urgency_label!r})"
        )


@dataclass
class RebalanceQueue:
    """Full rebalancing queue with regime context."""
    regime_state: str
    confidence: int
    trades: list[RebalanceEntry]
    trade_count: int
    timestamp: str
    data_age_sec: Optional[int]
    is_stale: bool

    @classmethod
    def from_dict(cls, d: dict) -> "RebalanceQueue":
        return cls(
            regime_state=d.get("regimeState", ""),
            confidence=d.get("confidence", 0),
            trades=[RebalanceEntry.from_dict(t) for t in d.get("trades", [])],
            trade_count=d.get("tradeCount", 0),
            timestamp=d.get("timestamp", ""),
            data_age_sec=d.get("dataAgeSec"),
            is_stale=d.get("isStale", False),
        )


@dataclass
class SignalReliability:
    """Reliability data for a single signal type."""
    signal_type: str
    label: str
    score: int
    reliability_label: str
    all_time_score: float
    current_rolling: float
    drop_pct: float
    is_decaying: bool
    freshness: str
    first_decay_date: Optional[str]

    @classmethod
    def from_dict(cls, key: str, d: dict) -> "SignalReliability":
        return cls(
            signal_type=key,
            label=d.get("label", key),
            score=d.get("score", 0),
            reliability_label=d.get("reliabilityLabel", "UNKNOWN"),
            all_time_score=d.get("allTimeScore", 0),
            current_rolling=d.get("currentRolling", 0),
            drop_pct=d.get("dropPct", 0),
            is_decaying=d.get("isDecaying", False),
            freshness=d.get("freshness", "Unknown"),
            first_decay_date=d.get("firstDecayDate"),
        )

    def __str__(self) -> str:
        decay_tag = " [DECAYING]" if self.is_decaying else ""
        return (
            f"SignalReliability({self.label}: score={self.score}, "
            f"freshness={self.freshness!r}{decay_tag})"
        )


@dataclass
class ReliabilityReport:
    """Full reliability report across all signal types."""
    window: int
    regime_alert: dict
    types: dict[str, SignalReliability]
    timestamp: str
    data_age_sec: Optional[int]
    is_stale: bool

    @classmethod
    def from_dict(cls, d: dict) -> "ReliabilityReport":
        types = {}
        for k, v in d.get("types", {}).items():
            types[k] = SignalReliability.from_dict(k, v)
        return cls(
            window=d.get("window", 0),
            regime_alert=d.get("regimeAlert", {}),
            types=types,
            timestamp=d.get("timestamp", ""),
            data_age_sec=d.get("dataAgeSec"),
            is_stale=d.get("isStale", False),
        )


@dataclass
class RegimeEvent:
    """A single regime transition in the history timeline."""
    date: str
    regime: str
    transition_from: Optional[str]

    @classmethod
    def from_dict(cls, d: dict) -> "RegimeEvent":
        return cls(
            date=d["date"],
            regime=d["regime"],
            transition_from=d.get("transitionFrom"),
        )

    def __str__(self) -> str:
        return f"RegimeEvent({self.date}: {self.transition_from} -> {self.regime})"


@dataclass
class RegimeHistory:
    """90-day regime timeline."""
    window_days: int
    current_regime: str
    transitions: list[RegimeEvent]
    transition_count: int
    timestamp: str
    data_age_sec: Optional[int]
    is_stale: bool

    @classmethod
    def from_dict(cls, d: dict) -> "RegimeHistory":
        return cls(
            window_days=d.get("windowDays", 90),
            current_regime=d.get("currentRegime", ""),
            transitions=[RegimeEvent.from_dict(t) for t in d.get("transitions", [])],
            transition_count=d.get("transitionCount", 0),
            timestamp=d.get("timestamp", ""),
            data_age_sec=d.get("dataAgeSec"),
            is_stale=d.get("isStale", False),
        )


@dataclass
class FilterRule:
    """Per-signal-type regime filter rule for the current regime."""
    signal_type: str
    label: str
    classification: str
    hit_rate: float
    n: int
    avg_ret: float

    @classmethod
    def from_dict(cls, key: str, d: dict) -> "FilterRule":
        return cls(
            signal_type=key,
            label=d.get("label", key),
            classification=d.get("classification", "AMBIGUOUS"),
            hit_rate=d.get("hitRate", 0),
            n=d.get("n", 0),
            avg_ret=d.get("avgRet", 0),
        )

    def __str__(self) -> str:
        return (
            f"FilterRule({self.label}: {self.classification}, "
            f"hitRate={self.hit_rate:.0%}, n={self.n}, avgRet={self.avg_ret:+.2f}%)"
        )


@dataclass
class FilteredSignal:
    """A single divergence signal with regime filter classification."""
    pair: str
    signal_type: str
    type_label: str
    conviction: int
    reliability: int
    reliability_label: str
    regime_filter: str
    regime_filter_hit_rate: float
    regime_filter_n: int
    regime_filter_avg_ret: float

    @classmethod
    def from_dict(cls, d: dict) -> "FilteredSignal":
        return cls(
            pair=d["pair"],
            signal_type=d["type"],
            type_label=d.get("typeLabel", d["type"]),
            conviction=d.get("conviction", 0),
            reliability=d.get("reliability", 0),
            reliability_label=d.get("reliabilityLabel", "UNKNOWN"),
            regime_filter=d.get("regimeFilter", "AMBIGUOUS"),
            regime_filter_hit_rate=d.get("regimeFilterHitRate", 0),
            regime_filter_n=d.get("regimeFilterN", 0),
            regime_filter_avg_ret=d.get("regimeFilterAvgRet", 0),
        )

    @property
    def is_actionable(self) -> bool:
        return self.regime_filter == "ACTIONABLE"

    @property
    def is_suppressed(self) -> bool:
        return self.regime_filter == "SUPPRESS"

    def __str__(self) -> str:
        return (
            f"FilteredSignal({self.pair} [{self.type_label}]: "
            f"{self.regime_filter}, conv={self.conviction})"
        )


@dataclass
class FilteredSignalReport:
    """Regime-conditional signal filter report."""
    regime_id: str
    regime_label: str
    regime_confidence: int
    total_signals: int
    actionable_count: int
    suppressed_count: int
    ambiguous_count: int
    filter_rules: dict[str, FilterRule]
    signals: list[FilteredSignal]
    timestamp: str
    data_age_sec: Optional[int]
    is_stale: bool

    @classmethod
    def from_dict(cls, d: dict) -> "FilteredSignalReport":
        rules = {}
        for k, v in d.get("filterRules", {}).items():
            rules[k] = FilterRule.from_dict(k, v)
        return cls(
            regime_id=d.get("regimeId", "NEUTRAL"),
            regime_label=d.get("regimeLabel", "Neutral"),
            regime_confidence=d.get("regimeConfidence", 0),
            total_signals=d.get("totalSignals", 0),
            actionable_count=d.get("actionableCount", 0),
            suppressed_count=d.get("suppressedCount", 0),
            ambiguous_count=d.get("ambiguousCount", 0),
            filter_rules=rules,
            signals=[FilteredSignal.from_dict(s) for s in d.get("signals", [])],
            timestamp=d.get("timestamp", ""),
            data_age_sec=d.get("dataAgeSec"),
            is_stale=d.get("isStale", False),
        )

    @property
    def actionable_signals(self) -> list[FilteredSignal]:
        return [s for s in self.signals if s.is_actionable]

    @property
    def suppressed_signals(self) -> list[FilteredSignal]:
        return [s for s in self.signals if s.is_suppressed]

    def __str__(self) -> str:
        return (
            f"FilteredSignalReport(regime={self.regime_id}, "
            f"actionable={self.actionable_count}, "
            f"suppressed={self.suppressed_count}, "
            f"ambiguous={self.ambiguous_count})"
        )


@dataclass
class HealthStatus:
    """API health check response."""
    status: str
    uptime: int
    uptime_human: str
    last_refresh: str
    data_age_sec: Optional[int]
    is_stale: bool
    refresh_count: int
    data_fresh: bool
    last_error: Optional[str]
    schema_version: str

    @classmethod
    def from_dict(cls, d: dict) -> "HealthStatus":
        return cls(
            status=d.get("status", "unknown"),
            uptime=d.get("uptime", 0),
            uptime_human=d.get("uptimeHuman", ""),
            last_refresh=d.get("lastRefresh", "pending"),
            data_age_sec=d.get("dataAgeSec"),
            is_stale=d.get("isStale", False),
            refresh_count=d.get("refreshCount", 0),
            data_fresh=d.get("dataFresh", False),
            last_error=d.get("lastError"),
            schema_version=d.get("schemaVersion", ""),
        )

    def __str__(self) -> str:
        return (
            f"HealthStatus(status={self.status!r}, "
            f"uptime={self.uptime_human}, "
            f"data_age={self.data_age_sec}s, "
            f"refreshes={self.refresh_count})"
        )

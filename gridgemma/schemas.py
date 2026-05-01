"""Shared data structures for GridGemma Pro."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


SEASONALITY_PHASES = {"summer", "winter", "flat"}


@dataclass(slots=True)
class EventAnomaly:
    """A bounded monthly anomaly applied only to synthetic profiles."""

    label: str
    start_month: int
    end_month: int
    multiplier: float
    reason: str

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "EventAnomaly | None":
        try:
            start_month = int(value.get("start_month", 0))
            end_month = int(value.get("end_month", 0))
        except (TypeError, ValueError):
            return None

        if not 1 <= start_month <= 12 or not 1 <= end_month <= 12:
            return None

        try:
            multiplier = float(value.get("multiplier", 1.0))
        except (TypeError, ValueError):
            multiplier = 1.0

        multiplier = clamp(multiplier, 0.75, 1.30)
        label = str(value.get("label") or "Synthetic event anomaly").strip()
        reason = str(value.get("reason") or "Generated from permissioned public context.").strip()

        return cls(
            label=label[:160],
            start_month=start_month,
            end_month=end_month,
            multiplier=multiplier,
            reason=reason[:300],
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class LLMParameters:
    """Behavioral shaping parameters returned by local Gemma 4 or fallback heuristics."""

    base_load_ratio: float = 0.45
    summer_peak_multiplier: float = 1.10
    winter_peak_multiplier: float = 0.95
    daily_morning_peak: float = 0.85
    daily_evening_peak: float = 1.10
    weekend_drop: float = 0.88
    noise_level: float = 0.03
    seasonality_phase: str = "summer"
    event_anomalies: list[EventAnomaly] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: dict[str, Any], allow_events: bool) -> "LLMParameters":
        params = cls(
            base_load_ratio=clamp(to_float(raw.get("base_load_ratio"), 0.45), 0.20, 0.85),
            summer_peak_multiplier=clamp(
                to_float(raw.get("summer_peak_multiplier"), 1.10), 0.70, 1.40
            ),
            winter_peak_multiplier=clamp(
                to_float(raw.get("winter_peak_multiplier"), 0.95), 0.70, 1.40
            ),
            daily_morning_peak=clamp(to_float(raw.get("daily_morning_peak"), 0.85), 0.50, 1.30),
            daily_evening_peak=clamp(to_float(raw.get("daily_evening_peak"), 1.10), 0.50, 1.40),
            weekend_drop=clamp(to_float(raw.get("weekend_drop"), 0.88), 0.55, 1.00),
            noise_level=clamp(to_float(raw.get("noise_level"), 0.03), 0.00, 0.06),
            seasonality_phase=str(raw.get("seasonality_phase") or "summer").lower().strip(),
            event_anomalies=[],
        )
        if params.seasonality_phase not in SEASONALITY_PHASES:
            params.seasonality_phase = "flat"

        if allow_events:
            raw_events = raw.get("event_anomalies", [])
            if isinstance(raw_events, list):
                for item in raw_events[:8]:
                    if isinstance(item, dict):
                        anomaly = EventAnomaly.from_dict(item)
                        if anomaly is not None:
                            params.event_anomalies.append(anomaly)

        return params

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["event_anomalies"] = [event.to_dict() for event in self.event_anomalies]
        return data


@dataclass(slots=True)
class GridInputs:
    country: str
    target_year: int
    annual_twh: float
    peak_mw: float
    climate_profile: str
    economic_profile: str
    local_model_path: str
    random_seed: int
    load_factor: float


@dataclass(slots=True)
class WebSnippet:
    title: str
    body: str
    url: str

    def to_dict(self) -> dict[str, str]:
        return {"title": self.title, "body": self.body, "url": self.url}


@dataclass(slots=True)
class ParameterResult:
    parameters: LLMParameters
    fallback_used: bool
    local_model_used: bool
    status_message: str
    raw_response: str | None = None


@dataclass(slots=True)
class ScenarioResult:
    scenario_label: str
    event_anomalies: list[EventAnomaly]
    fallback_used: bool
    local_model_used: bool
    status_message: str
    raw_response: str | None = None


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

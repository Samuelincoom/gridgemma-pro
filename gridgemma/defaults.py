"""Deterministic fallback behavior parameters."""

from __future__ import annotations

import sys
from pathlib import Path

from .schemas import LLMParameters, clamp


CLIMATE_PRESETS = [
    "Tropical, high cooling demand",
    "Tropical, moderate cooling demand",
    "Arid, high cooling demand",
    "Temperate, winter heating demand",
    "Mixed seasonal climate",
]

ECONOMIC_PRESETS = [
    "Residential dominated",
    "Tourism and services, low industry",
    "Industrial load dominant",
    "Agriculture and irrigation significant",
    "Mining or heavy industry significant",
    "Urbanizing mixed economy",
]

DEFAULT_MODEL_FILENAME = "gemma-4-e4b-it-q4.gguf"
DEFAULT_MODEL_RELATIVE_PATH = f"models/{DEFAULT_MODEL_FILENAME}"
MODEL_PREFERENCE_TERMS = ("gemma-4", "e2b", "e4b", "q4", "it")


def get_app_base_dir() -> Path:
    """Return the project root in development or the app folder when frozen."""

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def get_models_dir() -> Path:
    return get_app_base_dir() / "models"


def get_assets_dir() -> Path:
    return get_app_base_dir() / "assets"


def get_outputs_dir() -> Path:
    path = get_app_base_dir() / "outputs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def find_preferred_gguf_model(models_dir: Path | None = None) -> Path | None:
    """Find the best local GGUF model, preferring Gemma 4 instruction Q4 names."""

    folder = models_dir or get_models_dir()
    if not folder.exists():
        return None

    candidates = sorted(path for path in folder.glob("*.gguf") if path.is_file())
    if not candidates:
        return None

    def score(path: Path) -> tuple[int, int, str]:
        name = path.name.lower()
        preference_score = sum(1 for term in MODEL_PREFERENCE_TERMS if term in name)
        exact_bonus = 3 if name == DEFAULT_MODEL_FILENAME else 0
        return preference_score + exact_bonus, -len(name), name

    return max(candidates, key=score)


def fallback_parameters(climate_profile: str, economic_profile: str) -> LLMParameters:
    """Return sensible deterministic shaping values for offline heuristic mode."""

    climate = climate_profile.lower()
    economy = economic_profile.lower()

    params = LLMParameters()

    if "arid" in climate or "high cooling" in climate:
        params.summer_peak_multiplier = 1.20
        params.winter_peak_multiplier = 0.88
        params.seasonality_phase = "summer"
    elif "tropical" in climate and "moderate" in climate:
        params.summer_peak_multiplier = 1.08
        params.winter_peak_multiplier = 0.96
        params.seasonality_phase = "summer"
    elif "temperate" in climate or "winter heating" in climate:
        params.summer_peak_multiplier = 0.94
        params.winter_peak_multiplier = 1.20
        params.seasonality_phase = "winter"
    elif "mixed" in climate:
        params.summer_peak_multiplier = 1.06
        params.winter_peak_multiplier = 1.08
        params.seasonality_phase = "flat"
    else:
        params.summer_peak_multiplier = 1.06
        params.winter_peak_multiplier = 1.00
        params.seasonality_phase = "flat"

    if "residential" in economy:
        params.base_load_ratio = 0.38
        params.daily_morning_peak = 0.98
        params.daily_evening_peak = 1.20
        params.weekend_drop = 0.88
        params.noise_level = 0.035
    elif "tourism" in economy or "services" in economy:
        params.base_load_ratio = 0.40
        params.daily_morning_peak = 0.82
        params.daily_evening_peak = 1.18
        params.weekend_drop = 0.96
        params.summer_peak_multiplier = clamp(params.summer_peak_multiplier + 0.04, 0.70, 1.40)
        params.noise_level = 0.040
    elif "industrial" in economy:
        params.base_load_ratio = 0.58
        params.daily_morning_peak = 0.72
        params.daily_evening_peak = 0.82
        params.weekend_drop = 0.93
        params.noise_level = 0.020
    elif "agriculture" in economy or "irrigation" in economy:
        params.base_load_ratio = 0.46
        params.daily_morning_peak = 0.78
        params.daily_evening_peak = 0.92
        params.weekend_drop = 0.91
        params.summer_peak_multiplier = clamp(params.summer_peak_multiplier + 0.03, 0.70, 1.40)
        params.noise_level = 0.030
    elif "mining" in economy or "heavy industry" in economy:
        params.base_load_ratio = 0.70
        params.daily_morning_peak = 0.62
        params.daily_evening_peak = 0.70
        params.weekend_drop = 0.98
        params.noise_level = 0.015
    elif "urbanizing" in economy:
        params.base_load_ratio = 0.44
        params.daily_morning_peak = 0.90
        params.daily_evening_peak = 1.08
        params.weekend_drop = 0.90
        params.noise_level = 0.035

    params.event_anomalies = []
    return params

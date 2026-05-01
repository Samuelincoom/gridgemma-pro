"""Deterministic hourly load-curve synthesis."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy.optimize import brentq

from .schemas import EventAnomaly, GridInputs, LLMParameters, clamp


def make_hourly_index(year: int) -> pd.DatetimeIndex:
    """Create exactly 8,760 timezone-naive hours, excluding Feb 29 in leap years."""

    index = pd.date_range(
        start=f"{year}-01-01 00:00",
        end=f"{year}-12-31 23:00",
        freq="h",
    )
    index = index[~((index.month == 2) & (index.day == 29))]
    if len(index) != 8760:
        raise ValueError(f"Expected 8760 hourly timestamps, got {len(index)}.")
    return index


def synthesize_load_curve(inputs: GridInputs, parameters: LLMParameters) -> pd.DataFrame:
    """Generate a synthetic load curve that exactly matches annual TWh and peak MW."""

    index = make_hourly_index(inputs.target_year)
    profile = _build_raw_profile(index, inputs, parameters)

    profile = np.asarray(profile, dtype=float)
    profile = np.nan_to_num(profile, nan=0.0, posinf=0.0, neginf=0.0)
    profile = np.clip(profile, 1e-9, None)
    profile = profile / profile.max()

    load = _scale_profile_to_energy_and_peak(
        profile=profile,
        annual_twh=inputs.annual_twh,
        peak_mw=inputs.peak_mw,
        target_load_factor=inputs.load_factor,
    )

    df = pd.DataFrame({"snapshot": index, "p_set": load})
    actual_peak = float(df["p_set"].max())
    actual_twh = float(df["p_set"].sum() / 1_000_000.0)
    if abs(actual_peak - inputs.peak_mw) >= 1e-6:
        raise AssertionError("Peak scaling failed to preserve the target peak MW.")
    if abs(actual_twh - inputs.annual_twh) >= 1e-6:
        raise AssertionError("Energy scaling failed to preserve the target annual TWh.")
    return df


def calculate_statistics(df: pd.DataFrame, annual_twh: float, peak_mw: float) -> dict[str, float]:
    timestamps = pd.DatetimeIndex(df["snapshot"])
    values = df["p_set"].astype(float)
    weekend = timestamps.weekday >= 5
    weekday_average = float(values.loc[~weekend].mean())
    weekend_average = float(values.loc[weekend].mean())
    return {
        "annual_energy_target_twh": float(annual_twh),
        "actual_annual_energy_twh": float(values.sum() / 1_000_000.0),
        "peak_target_mw": float(peak_mw),
        "actual_peak_mw": float(values.max()),
        "load_factor": float(values.mean() / peak_mw),
        "min_load_mw": float(values.min()),
        "mean_load_mw": float(values.mean()),
        "weekday_average_mw": weekday_average,
        "weekend_average_mw": weekend_average,
        "weekend_to_weekday_ratio": float(weekend_average / weekday_average)
        if weekday_average
        else math.nan,
    }


def _build_raw_profile(
    index: pd.DatetimeIndex,
    inputs: GridInputs,
    parameters: LLMParameters,
) -> np.ndarray:
    hours = index.hour.to_numpy(dtype=float)
    n = len(index)
    year_position = np.arange(n, dtype=float) / n

    economy = inputs.economic_profile.lower()
    climate = inputs.climate_profile.lower()

    base_ratio = parameters.base_load_ratio
    morning_weight = 0.22 * parameters.daily_morning_peak
    evening_weight = 0.26 * parameters.daily_evening_peak
    daytime_weight = 0.13
    overnight_weight = -0.06
    seasonal_strength = _seasonal_strength(climate, economy)
    weekend_drop = parameters.weekend_drop

    if "industrial" in economy:
        base_ratio = max(base_ratio, 0.55)
        morning_weight *= 0.60
        evening_weight *= 0.60
        daytime_weight = 0.18
        overnight_weight = -0.025
        weekend_drop = max(weekend_drop, 0.92)
        seasonal_strength *= 0.75
    elif "mining" in economy or "heavy industry" in economy:
        base_ratio = max(base_ratio, 0.68)
        morning_weight *= 0.45
        evening_weight *= 0.45
        daytime_weight = 0.11
        overnight_weight = -0.015
        weekend_drop = max(weekend_drop, 0.97)
        seasonal_strength *= 0.55
    elif "residential" in economy:
        morning_weight *= 1.12
        evening_weight *= 1.18
        daytime_weight = 0.08
        weekend_drop = min(weekend_drop, 0.91)
    elif "tourism" in economy or "services" in economy:
        evening_weight *= 1.15
        daytime_weight = 0.12
        weekend_drop = max(weekend_drop, 0.95)
        seasonal_strength *= 1.15
    elif "agriculture" in economy or "irrigation" in economy:
        daytime_weight = 0.23
        morning_weight *= 0.85
        evening_weight *= 0.80
        seasonal_strength *= 1.10
    elif "urbanizing" in economy:
        morning_weight *= 1.04
        evening_weight *= 1.04
        daytime_weight = 0.12

    base_ratio = clamp(base_ratio, 0.20, 0.85)

    morning = _circular_gaussian(hours, center=8.0, width=2.0)
    evening = _circular_gaussian(hours, center=19.5, width=2.4)
    daytime = _circular_gaussian(hours, center=13.0, width=4.6)
    overnight = _circular_gaussian(hours, center=3.0, width=3.2)

    daily_component = (
        0.72
        + morning_weight * morning
        + evening_weight * evening
        + daytime_weight * daytime
        + overnight_weight * overnight
    )
    daily_component = np.clip(daily_component, 0.20, None)
    daily_component = daily_component / daily_component.mean()

    seasonal_component = _seasonal_component(year_position, parameters, seasonal_strength)
    raw_profile = base_ratio + (1.0 - base_ratio) * daily_component * seasonal_component

    is_weekend = index.weekday >= 5
    raw_profile[is_weekend] *= weekend_drop

    raw_profile = _apply_event_anomalies(index, raw_profile, parameters.event_anomalies)
    raw_profile = _apply_smoothed_noise(raw_profile, parameters.noise_level, inputs.random_seed)

    return np.clip(raw_profile, 1e-8, None)


def _seasonal_strength(climate: str, economy: str) -> float:
    strength = 0.15
    if "high cooling" in climate or "arid" in climate:
        strength = 0.22
    elif "temperate" in climate or "winter heating" in climate:
        strength = 0.20
    elif "tropical" in climate:
        strength = 0.11
    elif "mixed" in climate:
        strength = 0.14
    if "mining" in economy or "industrial" in economy:
        strength *= 0.85
    return strength


def _seasonal_component(
    year_position: np.ndarray,
    parameters: LLMParameters,
    seasonal_strength: float,
) -> np.ndarray:
    summer_wave = 0.5 + 0.5 * np.cos(2.0 * np.pi * (year_position - 0.58))
    winter_wave = 0.5 + 0.5 * np.cos(2.0 * np.pi * year_position)

    summer_effect = (parameters.summer_peak_multiplier - 1.0) * summer_wave
    winter_effect = (parameters.winter_peak_multiplier - 1.0) * winter_wave

    if parameters.seasonality_phase == "summer":
        combined = 1.0 + seasonal_strength * (2.2 * summer_effect + 0.8 * winter_effect)
    elif parameters.seasonality_phase == "winter":
        combined = 1.0 + seasonal_strength * (0.8 * summer_effect + 2.2 * winter_effect)
    else:
        combined = 1.0 + seasonal_strength * 0.65 * (summer_effect + winter_effect)

    return np.clip(combined, 0.65, 1.45)


def _apply_event_anomalies(
    index: pd.DatetimeIndex,
    profile: np.ndarray,
    anomalies: list[EventAnomaly],
) -> np.ndarray:
    adjusted = profile.copy()
    for anomaly in anomalies:
        start_month = clamp(float(anomaly.start_month), 1, 12)
        end_month = clamp(float(anomaly.end_month), 1, 12)
        start_int = int(min(start_month, end_month))
        end_int = int(max(start_month, end_month))
        multiplier = clamp(float(anomaly.multiplier), 0.75, 1.30)
        mask = (index.month >= start_int) & (index.month <= end_int)
        adjusted[mask] *= multiplier
    return adjusted


def _apply_smoothed_noise(profile: np.ndarray, noise_level: float, seed: int) -> np.ndarray:
    if noise_level <= 0:
        return profile

    rng = np.random.default_rng(seed)
    raw_noise = rng.normal(loc=0.0, scale=noise_level, size=len(profile))
    kernel_size = 9
    kernel = np.ones(kernel_size, dtype=float) / kernel_size
    smooth_noise = np.convolve(raw_noise, kernel, mode="same")
    multiplier = np.clip(1.0 + smooth_noise, 1.0 - 4.0 * noise_level, 1.0 + 4.0 * noise_level)
    return profile * multiplier


def _scale_profile_to_energy_and_peak(
    *,
    profile: np.ndarray,
    annual_twh: float,
    peak_mw: float,
    target_load_factor: float,
) -> np.ndarray:
    """Scale by gamma so max stays at one while mean equals the target load factor."""

    if target_load_factor >= 1.0 - 1e-14:
        load = np.full_like(profile, peak_mw, dtype=float)
        return _correct_energy_preserving_peak(load, annual_twh, peak_mw)

    def mean_at_gamma(gamma: float) -> float:
        return float(np.mean(np.power(profile, gamma)))

    def objective(gamma: float) -> float:
        return mean_at_gamma(gamma) - target_load_factor

    lower = 0.0
    upper = 1.0
    while objective(upper) > 0.0 and upper < 2048.0:
        upper *= 2.0

    if objective(upper) > 0.0:
        # Extremely flat raw profiles can make the exponent search ill-conditioned.
        # A monotone binary fallback still finds the closest feasible exponent.
        for _ in range(200):
            middle = (lower + upper) / 2.0
            if objective(middle) > 0.0:
                lower = middle
            else:
                upper = middle
        gamma = upper
    else:
        gamma = brentq(objective, lower, upper, xtol=1e-14, rtol=1e-14, maxiter=200)

    load = peak_mw * np.power(profile, gamma)
    max_mask = np.isclose(profile, 1.0, rtol=0.0, atol=1e-12)
    load[max_mask] = peak_mw
    return _correct_energy_preserving_peak(load, annual_twh, peak_mw)


def _correct_energy_preserving_peak(
    load: np.ndarray,
    annual_twh: float,
    peak_mw: float,
) -> np.ndarray:
    target_sum = annual_twh * 1_000_000.0
    load = np.asarray(load, dtype=float).copy()
    peak_mask = np.isclose(load, peak_mw, rtol=0.0, atol=1e-9)
    if not peak_mask.any():
        load[np.argmax(load)] = peak_mw
        peak_mask = np.isclose(load, peak_mw, rtol=0.0, atol=1e-9)

    adjustable = ~peak_mask
    delta = target_sum - float(load.sum())
    if adjustable.any() and abs(delta) > 1e-10:
        load[adjustable] += delta / int(adjustable.sum())

    load = np.clip(load, 0.0, peak_mw)
    # One final tiny correction compensates for clipping or floating point noise.
    adjustable = ~np.isclose(load, peak_mw, rtol=0.0, atol=1e-9)
    delta = target_sum - float(load.sum())
    if adjustable.any() and abs(delta) > 1e-10:
        load[adjustable] += delta / int(adjustable.sum())
        load = np.clip(load, 0.0, peak_mw)

    load[np.argmax(load)] = peak_mw
    return load


def _circular_gaussian(hours: np.ndarray, center: float, width: float) -> np.ndarray:
    distance = np.minimum(np.abs(hours - center), 24.0 - np.abs(hours - center))
    return np.exp(-0.5 * np.square(distance / width))

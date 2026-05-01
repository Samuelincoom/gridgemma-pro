"""Matplotlib plotting helpers."""

from __future__ import annotations

import pandas as pd
from matplotlib.axes import Axes


VIEW_FIRST_TWO_WEEKS = "first_two_weeks"
VIEW_PEAK_MONTH = "peak_month"
VIEW_FULL_YEAR = "full_year"


def plot_load_curve(ax: Axes, df: pd.DataFrame, country: str, year: int, view: str) -> None:
    ax.clear()
    data = df.copy()
    data["snapshot"] = pd.to_datetime(data["snapshot"])
    data = data.set_index("snapshot")

    if view == VIEW_PEAK_MONTH:
        peak_timestamp = data["p_set"].idxmax()
        month_data = data.loc[data.index.month == peak_timestamp.month]
        ax.plot(month_data.index, month_data["p_set"], color="#56B6C2", linewidth=1.3)
        ax.set_title(f"{country} {year} synthetic load - peak month")
    elif view == VIEW_FULL_YEAR:
        daily = data["p_set"].resample("D").mean()
        ax.plot(daily.index, daily, color="#98C379", linewidth=1.5)
        ax.set_title(f"{country} {year} synthetic load - daily average")
    else:
        preview = data.iloc[: 24 * 14]
        ax.plot(preview.index, preview["p_set"], color="#61AFEF", linewidth=1.4)
        ax.set_title(f"{country} {year} synthetic load - first 2 weeks")

    ax.set_xlabel("Snapshot")
    ax.set_ylabel("Load (MW)")
    ax.grid(True, alpha=0.25)
    ax.figure.autofmt_xdate()

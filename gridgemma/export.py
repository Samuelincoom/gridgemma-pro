"""CSV and metadata export helpers."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from .schemas import GridInputs, LLMParameters, WebSnippet
from .synthesizer import calculate_statistics


DISCLAIMER = (
    "Synthetic load curve generated from user inputs, local model parameters, and mathematical "
    "shaping. Not measured historical demand."
)


def default_csv_filename(country: str, year: int) -> str:
    return f"gridgemma_{slugify(country)}_{year}_load_curve.csv"


def default_metadata_filename(country: str, year: int) -> str:
    return f"gridgemma_{slugify(country)}_{year}_metadata.json"


def export_pypsa_csv(df: pd.DataFrame, path: str | Path) -> None:
    output = df[["snapshot", "p_set"]].copy()
    output["snapshot"] = pd.to_datetime(output["snapshot"]).dt.strftime("%Y-%m-%d %H:%M:%S")
    output.to_csv(path, index=False)


def export_metadata_json(metadata: dict[str, Any], path: str | Path) -> None:
    Path(path).write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def build_metadata(
    *,
    inputs: GridInputs,
    df: pd.DataFrame,
    parameters: LLMParameters,
    snippets: list[WebSnippet],
    local_model_used: bool,
    fallback_used: bool,
    web_search_used: bool,
) -> dict[str, Any]:
    stats = calculate_statistics(df, inputs.annual_twh, inputs.peak_mw)
    return {
        "country": inputs.country,
        "target_year": inputs.target_year,
        "annual_TWh": inputs.annual_twh,
        "peak_MW": inputs.peak_mw,
        "load_factor": inputs.load_factor,
        "climate_profile": inputs.climate_profile,
        "economic_profile": inputs.economic_profile,
        "model_runtime": "llama-cpp-python",
        "local_model_path": inputs.local_model_path,
        "local_model_used": local_model_used,
        "fallback_used": fallback_used,
        "web_search_used": web_search_used,
        "web_snippets_used": [snippet.to_dict() for snippet in snippets] if web_search_used else [],
        "llm_parameters": parameters.to_dict(),
        "event_anomalies": [event.to_dict() for event in parameters.event_anomalies],
        "random_seed": inputs.random_seed,
        "actual_annual_TWh": stats["actual_annual_energy_twh"],
        "actual_peak_MW": stats["actual_peak_mw"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "maker": "S. INC",
        "disclaimer": DISCLAIMER,
    }


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", value.strip()).strip("_").lower()
    return cleaned or "region"

"""Local Gemma 4 GGUF inference through llama-cpp-python."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .defaults import (
    DEFAULT_MODEL_RELATIVE_PATH,
    fallback_parameters,
    find_preferred_gguf_model,
    get_app_base_dir,
)
from .schemas import (
    EventAnomaly,
    GridInputs,
    LLMParameters,
    ParameterResult,
    ScenarioResult,
    WebSnippet,
)

RUNTIME_NAME = "llama-cpp-python"
DEFAULT_N_CTX = 4096
DEFAULT_TEMPERATURE = 0.2
DEFAULT_MAX_TOKENS = 512

_LOADED_MODEL: Any | None = None
_LOADED_MODEL_PATH: Path | None = None


def app_root() -> Path:
    return get_app_base_dir()


def default_model_path() -> Path:
    return find_preferred_gguf_model() or app_root() / DEFAULT_MODEL_RELATIVE_PATH


def resolve_model_path(model_path: str | Path | None) -> Path:
    value = str(model_path or "").strip()
    if not value:
        return default_model_path()
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = app_root() / path
    if path.is_dir():
        return find_preferred_gguf_model(path) or (path / Path(DEFAULT_MODEL_RELATIVE_PATH).name)
    return path.resolve()


def check_offline_ai_status(model_path: str | Path | None = None) -> dict[str, str | bool]:
    path = resolve_model_path(model_path)
    found = path.is_file() and path.suffix.lower() == ".gguf"
    return {
        "path": str(path),
        "found": found,
        "runtime": RUNTIME_NAME,
        "ai_mode": "Local Gemma 4" if found else "Fallback heuristic",
        "internet_status": "OFF by default",
    }


def get_behavior_parameters(
    inputs: GridInputs,
    model_path: str | Path | None = None,
) -> ParameterResult:
    """Ask local Gemma 4 for shaping parameters, falling back deterministically."""

    fallback = fallback_parameters(inputs.climate_profile, inputs.economic_profile)
    resolved_path = resolve_model_path(model_path or inputs.local_model_path)
    if not resolved_path.is_file():
        return ParameterResult(
            parameters=fallback,
            fallback_used=True,
            local_model_used=False,
            status_message=(
                "No local Gemma 4 GGUF model found. Place a .gguf file in models/ or run "
                "download_model.bat. Generated using fallback heuristic engine."
            ),
        )

    try:
        raw_response = _generate_text(resolved_path, _build_behavior_prompt(inputs))
        parsed = parse_json_object(raw_response)
        params = LLMParameters.from_dict(parsed, allow_events=False)
        params.event_anomalies = []
        return ParameterResult(
            parameters=params,
            fallback_used=False,
            local_model_used=True,
            status_message="Local Gemma 4 parameters applied.",
            raw_response=raw_response,
        )
    except Exception as exc:
        return ParameterResult(
            parameters=fallback,
            fallback_used=True,
            local_model_used=False,
            status_message=(
                f"Local Gemma 4 failed gracefully ({exc}). Generated using fallback "
                "heuristic engine, not local Gemma 4."
            ),
        )


def get_future_scenario_anomalies(
    inputs: GridInputs,
    snippets: list[WebSnippet],
    model_path: str | Path | None = None,
) -> ScenarioResult:
    """Convert permissioned web snippets into bounded synthetic future anomalies."""

    if not snippets:
        return ScenarioResult(
            scenario_label="No future scenario snippets found",
            event_anomalies=[],
            fallback_used=True,
            local_model_used=False,
            status_message="No snippets available for future scenario analysis.",
        )

    resolved_path = resolve_model_path(model_path or inputs.local_model_path)
    if not resolved_path.is_file():
        return _keyword_scenario_fallback(
            snippets,
            "No local Gemma 4 GGUF model found. Future snippets summarized with keyword fallback.",
        )

    try:
        raw_response = _generate_text(resolved_path, _build_scenario_prompt(inputs, snippets))
        parsed = parse_json_object(raw_response)
        events = []
        raw_events = parsed.get("event_anomalies", [])
        if isinstance(raw_events, list):
            for item in raw_events[:8]:
                if isinstance(item, dict):
                    anomaly = EventAnomaly.from_dict(item)
                    if anomaly is not None:
                        events.append(anomaly)

        label = str(parsed.get("scenario_label") or "Future news scenario").strip()[:160]
        return ScenarioResult(
            scenario_label=label,
            event_anomalies=events,
            fallback_used=False,
            local_model_used=True,
            status_message="Future scenario anomalies generated with local Gemma 4.",
            raw_response=raw_response,
        )
    except Exception as exc:
        return _keyword_scenario_fallback(
            snippets,
            f"Future scenario local model analysis failed gracefully ({exc}). "
            "Using keyword fallback.",
        )


def parse_json_object(text: str) -> dict[str, Any]:
    """Parse exact JSON or extract the first balanced JSON object from extra text."""

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    candidate = extract_first_json_object(text)
    parsed = json.loads(candidate)
    if not isinstance(parsed, dict):
        raise ValueError("JSON payload must be an object.")
    return parsed


def extract_first_json_object(text: str) -> str:
    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON object found.")

    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]

    raise ValueError("Unbalanced JSON object.")


def _generate_text(model_path: Path, prompt: str) -> str:
    model = _load_model(model_path)
    response = model(
        prompt,
        max_tokens=DEFAULT_MAX_TOKENS,
        temperature=DEFAULT_TEMPERATURE,
        echo=False,
        stop=["</s>", "<end_of_turn>"],
    )
    choices = response.get("choices", []) if isinstance(response, dict) else []
    if not choices:
        raise ValueError("Local model returned no text.")
    return str(choices[0].get("text", "")).strip()


def _load_model(model_path: Path) -> Any:
    global _LOADED_MODEL, _LOADED_MODEL_PATH
    if _LOADED_MODEL is not None and _LOADED_MODEL_PATH == model_path:
        return _LOADED_MODEL

    try:
        from llama_cpp import Llama
    except Exception as exc:
        raise RuntimeError("llama-cpp-python is not installed or could not be imported") from exc

    _LOADED_MODEL = Llama(
        model_path=str(model_path),
        n_ctx=DEFAULT_N_CTX,
        verbose=False,
    )
    _LOADED_MODEL_PATH = model_path
    return _LOADED_MODEL


def _build_behavior_prompt(inputs: GridInputs) -> str:
    return f"""
You are GridGemma Pro's local offline power-system load-shape assistant.
Return STRICT JSON only. No markdown. No explanation.

Inputs:
Country or region: {inputs.country}
Target year: {inputs.target_year}
Annual electricity consumption target: {inputs.annual_twh} TWh
Peak demand target: {inputs.peak_mw} MW
Computed target load factor: {inputs.load_factor:.6f}
Climate profile: {inputs.climate_profile}
Economic profile: {inputs.economic_profile}

Return this JSON shape exactly:
{{
  "base_load_ratio": 0.45,
  "summer_peak_multiplier": 1.10,
  "winter_peak_multiplier": 0.95,
  "daily_morning_peak": 0.85,
  "daily_evening_peak": 1.10,
  "weekend_drop": 0.88,
  "noise_level": 0.03,
  "seasonality_phase": "summer",
  "event_anomalies": []
}}

Rules:
- JSON only
- base_load_ratio between 0.20 and 0.85
- summer_peak_multiplier between 0.70 and 1.40
- winter_peak_multiplier between 0.70 and 1.40
- daily_morning_peak between 0.50 and 1.30
- daily_evening_peak between 0.50 and 1.40
- weekend_drop between 0.55 and 1.00
- noise_level between 0.00 and 0.06
- seasonality_phase one of ["summer", "winter", "flat"]
- event_anomalies must be []
- Never claim measured historical demand.
""".strip()


def _build_scenario_prompt(inputs: GridInputs, snippets: list[WebSnippet]) -> str:
    context = []
    for i, snippet in enumerate(snippets, start=1):
        context.append(f"{i}. Title: {snippet.title}\nSnippet: {snippet.body}\nSource: {snippet.url}")

    return f"""
You are GridGemma Pro's local offline scenario assistant.
Return STRICT JSON only. No markdown. No explanation.

Country or region: {inputs.country}
Target year: {inputs.target_year}
Climate profile: {inputs.climate_profile}
Economic profile: {inputs.economic_profile}

Permissioned public search snippets:
{chr(10).join(context)}

Return this JSON shape:
{{
  "scenario_label": "Planned grid expansion and demand growth",
  "event_anomalies": [
    {{
      "label": "New industrial demand from planned project",
      "start_month": 6,
      "end_month": 12,
      "multiplier": 1.06,
      "reason": "Public snippets suggest new electricity-intensive project."
    }}
  ]
}}

Rules:
- JSON only
- Use only the snippets above.
- Multipliers must remain between 0.75 and 1.30.
- Use empty event_anomalies if snippets do not justify a synthetic anomaly.
- Never claim measured historical demand.
""".strip()


def _keyword_scenario_fallback(snippets: list[WebSnippet], status_message: str) -> ScenarioResult:
    text = " ".join(f"{snippet.title} {snippet.body}" for snippet in snippets).lower()
    events: list[EventAnomaly] = []
    label = "Keyword-based future scenario"

    growth_terms = [
        "planned",
        "project",
        "power plant",
        "grid expansion",
        "renewable",
        "industrial",
        "mining",
        "data center",
        "factory",
        "rail",
    ]
    stress_terms = ["crisis", "drought", "heatwave", "shortage", "fuel", "rationing", "outage"]

    if any(term in text for term in growth_terms):
        events.append(
            EventAnomaly(
                label="Potential future demand growth from planned projects",
                start_month=6,
                end_month=12,
                multiplier=1.06,
                reason="Keyword fallback found public snippets mentioning planned energy or infrastructure projects.",
            )
        )
        label = "Planned project demand-growth scenario"

    if any(term in text for term in stress_terms):
        events.append(
            EventAnomaly(
                label="Potential future demand stress from energy or climate event",
                start_month=7,
                end_month=9,
                multiplier=1.04,
                reason="Keyword fallback found public snippets mentioning energy stress, weather stress, or shortages.",
            )
        )
        label = "Energy stress scenario"

    return ScenarioResult(
        scenario_label=label,
        event_anomalies=events[:5],
        fallback_used=True,
        local_model_used=False,
        status_message=status_message,
    )

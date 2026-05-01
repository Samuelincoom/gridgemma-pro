"""Input validation helpers."""

from __future__ import annotations

import random
from pathlib import Path
from dataclasses import dataclass, field

from .schemas import GridInputs


@dataclass(slots=True)
class ValidationResult:
    ok: bool
    inputs: GridInputs | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate_inputs(
    *,
    country: str,
    target_year: str,
    annual_twh: str,
    peak_mw: str,
    climate_profile: str,
    economic_profile: str,
    local_model_path: str,
    random_seed: str,
) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    clean_country = country.strip()
    if not clean_country:
        errors.append("Country or region name must not be empty.")

    try:
        year = int(target_year.strip())
    except ValueError:
        errors.append("Target year must be an integer.")
        year = 0

    try:
        annual = float(annual_twh.strip())
        if annual <= 0:
            errors.append("Total annual consumption must be positive.")
    except ValueError:
        errors.append("Total annual consumption must be a number.")
        annual = 0.0

    try:
        peak = float(peak_mw.strip())
        if peak <= 0:
            errors.append("Peak demand must be positive.")
    except ValueError:
        errors.append("Peak demand must be a number.")
        peak = 0.0

    seed_text = random_seed.strip()
    if seed_text:
        try:
            seed = int(seed_text)
        except ValueError:
            errors.append("Random seed must be an integer or left empty.")
            seed = 0
    else:
        seed = random.SystemRandom().randint(1, 2_147_483_647)

    model_path = local_model_path.strip()
    if model_path and Path(model_path).suffix.lower() != ".gguf":
        errors.append("Local model file must use the .gguf extension.")

    climate = climate_profile.strip() or "Mixed seasonal climate"
    economy = economic_profile.strip() or "Urbanizing mixed economy"

    load_factor = 0.0
    if annual > 0 and peak > 0:
        load_factor = annual * 1_000_000.0 / (peak * 8760.0)
        if load_factor > 1.0:
            errors.append(
                "Impossible target: annual energy is greater than the peak demand can physically supply."
            )
        elif load_factor < 0.05:
            warnings.append("Target load factor is extremely low; the curve will be very peaky.")
        elif load_factor > 0.90:
            warnings.append("Target load factor is very high; the load curve will be almost flat.")

    if errors:
        return ValidationResult(ok=False, errors=errors, warnings=warnings)

    return ValidationResult(
        ok=True,
        inputs=GridInputs(
            country=clean_country,
            target_year=year,
            annual_twh=annual,
            peak_mw=peak,
            climate_profile=climate,
            economic_profile=economy,
            local_model_path=model_path,
            random_seed=seed,
            load_factor=load_factor,
        ),
        warnings=warnings,
    )

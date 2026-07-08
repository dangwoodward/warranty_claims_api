"""
Warranty coverage logic.

In production this module would be provided to us (backed by a real warranty
database / rules engine). For this exercise it's a self-contained *stub* that
returns plausible results so the rest of the pipeline can be exercised end to
end. The public signature matches the one we were given:

    check_warranty_coverage(vin, make, model, year, mileage, part_number) -> dict
"""

from __future__ import annotations

import re
from datetime import date

# Makes we "know" about. An unknown make/model combination is treated as an
# input error, mirroring the documented `ValueError` contract.
_KNOWN_MAKES = {
    "chevrolet",
    "gmc",
    "buick",
    "cadillac",
}

# A 17-character VIN, excluding the letters I, O and Q (never used in real VINs).
_VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")


def _looks_like_ev(model: str, part_number: str) -> bool:
    """Heuristic: is this an EV / high-voltage-battery repair?"""
    model_l = model.lower()
    if "ev" in model_l or "bolt" in model_l or "volt" in model_l:
        return True
    # GM high-voltage battery module part numbers used in this exercise.
    return part_number.strip() in {"24299461"}


def check_warranty_coverage(
    vin: str,
    make: str,
    model: str,
    year: int,
    mileage: int,
    part_number: str,
) -> dict:
    """
    Checks warranty coverage eligibility for a vehicle and repair.

    Returns:
        {
            "eligible": bool,
            "reason": str,
            "warranty_type": str,  # e.g. "Voltec", "Powertrain", "Bumper-to-Bumper"
        }

    Raises:
        ValueError: If VIN format is invalid or make/model combination is unknown.
    """
    if not isinstance(vin, str) or not _VIN_RE.match(vin.upper()):
        raise ValueError(f"Invalid VIN format: {vin!r}")

    if make.strip().lower() not in _KNOWN_MAKES:
        raise ValueError(f"Unknown make/model combination: {make!r} {model!r}")

    # Vehicle age in years, floored at 0. We don't have an in-service date in a
    # repair order, so age-from-model-year is a reasonable stand-in.
    age_years = max(date.today().year - int(year), 0)
    mileage = int(mileage)

    # EV high-voltage battery components: GM "Voltec" 8yr / 100k coverage.
    if _looks_like_ev(model, part_number):
        eligible = age_years <= 8 and mileage <= 100_000
        return {
            "eligible": eligible,
            "reason": (
                "Vehicle within Voltec warranty: 8yr/100k miles"
                if eligible
                else f"Outside Voltec warranty (age {age_years}yr, {mileage} mi)"
            ),
            "warranty_type": "Voltec",
        }

    # Powertrain: 5yr / 60k.
    if age_years <= 5 and mileage <= 60_000:
        return {
            "eligible": True,
            "reason": "Vehicle within Powertrain warranty: 5yr/60k miles",
            "warranty_type": "Powertrain",
        }

    # Bumper-to-bumper: 3yr / 36k.
    eligible = age_years <= 3 and mileage <= 36_000
    return {
        "eligible": eligible,
        "reason": (
            "Vehicle within Bumper-to-Bumper warranty: 3yr/36k miles"
            if eligible
            else f"No active warranty coverage (age {age_years}yr, {mileage} mi)"
        ),
        "warranty_type": "Bumper-to-Bumper",
    }

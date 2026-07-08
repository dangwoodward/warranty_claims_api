"""Pydantic models for the request, LLM extraction schema, and API response."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AnalyzeClaimRequest(BaseModel):
    """Incoming request body for POST /analyze-claim."""

    ro_text: str = Field(..., description="Raw repair-order text to analyze.")


class ExtractedClaim(BaseModel):
    """
    Structured fields extracted from the repair-order text.

    This schema is handed to the LLM via structured output, so the field
    descriptions double as extraction instructions.
    """

    vin: str = Field(..., description="17-character Vehicle Identification Number.")
    year: int = Field(..., description="Model year, e.g. 2022.")
    make: str = Field(..., description="Manufacturer, e.g. Chevrolet.")
    model: str = Field(..., description="Model name, e.g. Bolt EV.")
    mileage: int = Field(
        ..., description="Odometer reading as an integer (strip commas), e.g. 12340."
    )
    repair_description: str = Field(
        ..., description="Short description of the repair performed."
    )
    part_number: str = Field(..., description="Primary part number used in the repair.")
    labor_hours: float = Field(..., description="Labor hours billed, e.g. 4.2.")


class AnalyzeClaimResponse(BaseModel):
    """Response body for POST /analyze-claim."""

    vin: str
    year: int
    make: str
    model: str
    mileage: int
    repair_description: str
    part_number: str
    labor_hours: float
    coverage_eligible: bool
    coverage_reason: str

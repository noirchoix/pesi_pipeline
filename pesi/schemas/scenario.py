from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TaxonObservation(BaseModel):
    scientific_name: str
    common_name: str | None = None
    probability: float | None = Field(default=None, ge=0, le=1)
    source: str | None = None
    raw: dict[str, Any] | None = None


class FieldScenario(BaseModel):
    scenario_id: str = "default_contextual_scenario"
    crop_taxa: list[str] = Field(default_factory=list)
    crop_family: list[str] = Field(default_factory=list)
    weed_taxa: list[str] = Field(default_factory=list)
    weed_family: list[str] = Field(default_factory=list)
    location: dict[str, Any] | None = None
    growth_stage: str | None = None
    plant_id_observations: list[TaxonObservation] = Field(default_factory=list)
    confidence_threshold: float = Field(default=0.70, ge=0, le=1)
    evidence_class: str = "user_or_api_supplied_context"

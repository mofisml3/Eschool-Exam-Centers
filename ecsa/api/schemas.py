from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field


class ParameterIn(BaseModel):
    param_key: str
    param_value: str
    governorate: str | None = None
    unit: str | None = None
    effective_from: date | None = None
    description: str | None = None


class ParameterOut(BaseModel):
    id: int
    param_key: str
    param_value: str
    unit: str | None
    governorate: str | None
    effective_from: date
    description: str | None

    model_config = {"from_attributes": True}


class RunIn(BaseModel):
    name: str
    governorate: str
    exam_round: int = 1
    round_start_date: date
    param_overrides: dict[str, Any] = Field(default_factory=dict)
    include_schools: list[str] = Field(default_factory=list)
    exclude_schools: list[str] = Field(default_factory=list)


class PreviewIn(BaseModel):
    governorate: str
    exam_round: int = 1
    param_overrides: dict[str, Any] = Field(default_factory=dict)
    include_schools: list[str] = Field(default_factory=list)
    exclude_schools: list[str] = Field(default_factory=list)


class ScenarioOut(BaseModel):
    scenario_id: int
    name: str
    governorate: str
    exam_round: int
    round_start_date: date
    status: str
    created_at: Any
    kpi_summary: dict
    params_snapshot: dict

    model_config = {"from_attributes": True}


class ScenarioDetailOut(ScenarioOut):
    decision_log: dict

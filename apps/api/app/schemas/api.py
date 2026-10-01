from typing import Literal

from pydantic import BaseModel, Field

Op = Literal["standardize_missing", "normalize_email", "standardize_phone", "parse_date",
             "convert_currency", "normalize_name", "impute_median", "remove_duplicates"]


class StepIn(BaseModel):
    operation: Op
    column: str = "*"
    enabled: bool = True


class CleanRequest(BaseModel):
    steps: list[StepIn] | None = None  # kosong = pakai semua rekomendasi


class PipelineCreate(BaseModel):
    dataset_id: str
    name: str = Field(min_length=1, max_length=120)
    steps: list[StepIn]


class PipelineRunRequest(BaseModel):
    dataset_id: str | None = None


class AIColumn(BaseModel):
    column: str
    semantic_type: str
    confidence: float = Field(ge=0, le=1)


class AIRecommendation(BaseModel):
    column: str
    issue: str
    recommendation: Op
    reason: str
    confidence: float = Field(ge=0, le=1)


class AIResult(BaseModel):
    columns: list[AIColumn]
    recommendations: list[AIRecommendation]

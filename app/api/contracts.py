from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ApiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class CandidateFilters(ApiModel):
    name: str | None = Field(default=None, max_length=200)
    party: str | None = Field(default=None, max_length=30)
    state: str | None = Field(default=None, min_length=2, max_length=2)
    office: str | None = Field(default=None, max_length=100)


class SearchRequest(ApiModel):
    query: str = Field(min_length=1, max_length=2_000)
    candidate_id: int | None = Field(default=None, alias="candidateId", gt=0)
    source_type: str | None = Field(default=None, alias="sourceType", max_length=40)
    top_k: int = Field(default=8, alias="topK", ge=1, le=50)

    @field_validator("query")
    @classmethod
    def reject_blank_query(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("query cannot be blank")
        return normalized


class AskRequest(ApiModel):
    question: str = Field(min_length=1, max_length=4_000)
    candidate_id: int | None = Field(default=None, alias="candidateId", gt=0)

    @field_validator("question")
    @classmethod
    def reject_blank_question(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("question cannot be blank")
        return normalized

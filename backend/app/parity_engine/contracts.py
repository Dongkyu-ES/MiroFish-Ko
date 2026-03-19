from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ExpectedOutput = Literal["graph", "search", "profile", "report", "memory_update"]
OntologyMode = Literal["generate", "inline"]
SearchScope = Literal["edges", "nodes", "hybrid"]
CutoverVerdict = Literal["fail", "shadow_only", "eligible_for_local_primary"]


class CorpusItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    language: str = "ko"
    purpose: str | None = None
    description: str | None = None
    documents: list[str] = Field(min_length=1)
    ontology_mode: OntologyMode = "generate"
    ontology: dict[str, Any] | None = None
    simulation_requirement: str = Field(min_length=1)
    queries: list[str] = Field(min_length=1)
    expected_outputs: list[ExpectedOutput] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_ontology(self) -> "CorpusItem":
        if self.ontology_mode == "inline" and not self.ontology:
            raise ValueError("inline ontology_mode requires ontology data")
        return self


class GraphSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)


class SearchSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1)
    scope: SearchScope
    edges: list[dict[str, Any]] = Field(default_factory=list)
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    facts: list[str] = Field(default_factory=list)


class ProfileSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context: str | None = None
    profiles: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReportSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_outputs: dict[str, Any] = Field(default_factory=dict)
    sections: list[dict[str, Any]] = Field(default_factory=list)
    chat_responses: list[dict[str, Any]] = Field(default_factory=list)


class MemoryUpdateSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    delta: dict[str, Any] = Field(default_factory=dict)
    episodes: list[str] = Field(default_factory=list)


class ParityScorecard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: CutoverVerdict = "fail"
    metrics: dict[str, float] = Field(default_factory=dict)
    thresholds: dict[str, float] = Field(default_factory=dict)


class BaselineSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    captured_at: str | None = None
    graph: GraphSnapshot
    search: list[SearchSnapshot] = Field(default_factory=list)
    profile: ProfileSnapshot = Field(default_factory=ProfileSnapshot)
    report: ReportSnapshot = Field(default_factory=ReportSnapshot)
    memory_update: MemoryUpdateSnapshot = Field(default_factory=MemoryUpdateSnapshot)
    scorecard: ParityScorecard = Field(default_factory=ParityScorecard)
    metadata: dict[str, Any] = Field(default_factory=dict)
    raw_api_examples: dict[str, Any] = Field(default_factory=dict)

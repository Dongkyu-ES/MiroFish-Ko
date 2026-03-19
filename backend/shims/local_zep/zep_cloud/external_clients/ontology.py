"""Pydantic-compatible ontology base classes for the local zep shim."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


EntityText = str


class EntityModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class EdgeModel(BaseModel):
    model_config = ConfigDict(extra="allow")

"""Local compatibility shim for zep_cloud."""

from __future__ import annotations

from dataclasses import dataclass


class InternalServerError(RuntimeError):
    """Compatibility exception used by paging utilities."""


@dataclass(slots=True)
class EpisodeData:
    data: str
    type: str = "text"


@dataclass(slots=True)
class EntityEdgeSourceTarget:
    source: str
    target: str


__all__ = [
    "EpisodeData",
    "EntityEdgeSourceTarget",
    "InternalServerError",
]

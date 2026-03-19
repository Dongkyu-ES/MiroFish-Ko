from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class EpisodeStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


@dataclass(slots=True)
class GraphRecord:
    graph_id: str
    name: str
    description: str
    created_at: datetime

    def __getitem__(self, key: str):
        return getattr(self, key)


@dataclass(slots=True)
class EpisodeRecord:
    episode_id: str
    graph_id: str
    body: str
    status: EpisodeStatus
    created_at: datetime
    updated_at: datetime
    error: str | None = None

    def __getitem__(self, key: str):
        return getattr(self, key)


@dataclass(slots=True)
class NodeRecord:
    uuid_: str
    graph_id: str
    name: str
    labels: list[str]
    summary: str
    attributes: dict
    created_at: datetime

    def __getitem__(self, key: str):
        return getattr(self, key)


@dataclass(slots=True)
class EdgeRecord:
    uuid_: str
    graph_id: str
    name: str
    fact: str
    source_node_uuid: str
    target_node_uuid: str
    attributes: dict
    created_at: datetime
    valid_at: datetime | None
    invalid_at: datetime | None
    expired_at: datetime | None
    episodes: list[str]
    fact_type: str | None = None

    def __getitem__(self, key: str):
        return getattr(self, key)

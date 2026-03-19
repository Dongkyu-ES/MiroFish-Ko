"""Convert MiroFish ontology JSON into Graphiti add_episode extraction inputs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from graphiti_core.nodes import EntityNode
from pydantic import BaseModel, Field, create_model

from .ontology import normalize_ontology

RESERVED_ENTITY_FIELDS = set(EntityNode.model_fields.keys())


@dataclass(slots=True)
class GraphitiExtractionConfig:
    entity_types: dict[str, type[BaseModel]]
    edge_types: dict[str, type[BaseModel]]
    edge_type_map: dict[tuple[str, str], list[str]]
    custom_extraction_instructions: str


def build_graphiti_extraction_config(ontology: dict[str, Any]) -> GraphitiExtractionConfig:
    normalized = normalize_ontology(ontology)
    entity_names = {entity["name"] for entity in normalized.get("entity_types", [])}

    entity_types = {
        entity["name"]: _create_entity_model(entity)
        for entity in normalized.get("entity_types", [])
    }
    edge_types = {
        edge["name"]: _create_edge_model(edge)
        for edge in normalized.get("edge_types", [])
    }

    edge_type_map: dict[tuple[str, str], list[str]] = {}
    for edge in normalized.get("edge_types", []):
        edge_name = edge["name"]
        for pair in edge.get("source_targets", []):
            source = pair.get("source")
            target = pair.get("target")
            if source not in entity_names or target not in entity_names:
                continue
            edge_type_map.setdefault((source, target), []).append(edge_name)

    instructions = _build_custom_extraction_instructions(normalized, edge_type_map)
    return GraphitiExtractionConfig(
        entity_types=entity_types,
        edge_types=edge_types,
        edge_type_map=edge_type_map,
        custom_extraction_instructions=instructions,
    )


def _create_entity_model(entity: dict[str, Any]) -> type[BaseModel]:
    fields = {}
    model = create_model(entity["name"], __base__=BaseModel, **fields)
    model.__doc__ = _compact_description(entity.get("description") or f"{entity['name']} entity type.")
    return model


def _create_edge_model(edge: dict[str, Any]) -> type[BaseModel]:
    fields = {}
    model = create_model(edge["name"], __base__=BaseModel, **fields)
    model.__doc__ = _compact_description(edge.get("description") or f"{edge['name']} relationship.")
    return model


def _safe_attribute_name(name: str) -> str:
    normalized = name.strip()
    if normalized.lower() in RESERVED_ENTITY_FIELDS:
        return f"entity_{normalized}"
    return normalized


def _build_custom_extraction_instructions(
    ontology: dict[str, Any],
    edge_type_map: dict[tuple[str, str], list[str]],
) -> str:
    edge_lines = []
    for (source, target), edge_names in sorted(edge_type_map.items()):
        edge_lines.append(f"- {source} -> {target}: {', '.join(sorted(edge_names))}")

    entity_lines = [f"- {entity['name']}" for entity in ontology.get("entity_types", [])]

    return "\n".join(
        [
            "Use only the ontology-defined entity and relationship types below.",
            "Prefer ontology edge names over generic relation labels.",
            "Emit relations only when the source/target signature is allowed.",
            "Entity types:",
            *entity_lines,
            "Allowed relationship signatures:",
            *edge_lines,
        ]
    )


def _compact_description(value: str, limit: int = 120) -> str:
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."

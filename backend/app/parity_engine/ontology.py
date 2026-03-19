"""Ontology normalization helpers for Graphiti parity overlays."""

from __future__ import annotations

import copy
import re
from typing import Any


def normalize_ontology(ontology: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(ontology)
    entity_name_map: dict[str, str] = {}
    normalized_entities = []
    for entity in ontology.get("entity_types", []):
        normalized_entity = _normalize_entity_type(entity)
        entity_name_map[str(entity.get("name", ""))] = normalized_entity["name"]
        normalized_entities.append(normalized_entity)
    normalized["entity_types"] = normalized_entities
    normalized["edge_types"] = [
        _normalize_edge_type(edge, entity_name_map) for edge in ontology.get("edge_types", [])
    ]
    return normalized


def _normalize_entity_type(entity: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(entity)
    name = _sanitize_entity_type_name(str(normalized["name"]))
    normalized["name"] = name
    normalized["description"] = normalized.get("description") or f"{name} entity type."
    normalized["attributes"] = normalized.get("attributes", [])
    return normalized


def _normalize_edge_type(edge: dict[str, Any], entity_name_map: dict[str, str]) -> dict[str, Any]:
    normalized = dict(edge)
    edge_name = _strip_instructional_suffix(str(normalized["name"]))
    normalized["name"] = _to_screaming_snake_case(edge_name)
    normalized["description"] = normalized.get("description") or f"{normalized['name']} relationship."
    normalized["source_targets"] = [
        {
            "source": entity_name_map.get(str(pair.get("source", "")), _sanitize_entity_type_name(str(pair.get("source", "")))),
            "target": entity_name_map.get(str(pair.get("target", "")), _sanitize_entity_type_name(str(pair.get("target", "")))),
        }
        for pair in normalized.get("source_targets", [])
    ]
    normalized["attributes"] = normalized.get("attributes", [])
    return normalized


def _to_screaming_snake_case(value: str) -> str:
    words = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value).replace("-", "_")
    words = re.sub(r"\s+", "_", words)
    return words.upper()


def _sanitize_entity_type_name(value: str) -> str:
    stripped = _strip_instructional_suffix(value)
    sanitized = re.sub(r"[^A-Za-z0-9_]+", "_", stripped).strip("_")
    sanitized = re.sub(r"_+", "_", sanitized)
    if not sanitized:
        return "Entity"
    if sanitized[0].isdigit():
        return f"_{sanitized}"
    return sanitized


def _strip_instructional_suffix(value: str) -> str:
    stripped = value.strip()
    stripped = re.sub(
        r"\s*\((?:[^)]*\b(?:PascalCase|UPPER_SNAKE_CASE|snake_case)\b[^)]*)\)\s*$",
        "",
        stripped,
        flags=re.IGNORECASE,
    )
    return stripped.strip()

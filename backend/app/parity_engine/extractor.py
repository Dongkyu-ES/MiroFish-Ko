"""LLM-only ontology-aware extraction overlay for parity tests."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from .ontology import normalize_ontology
from .resolver import EntityResolver


class GraphitiExtractionOverlay:
    def __init__(
        self,
        llm_client: Any | None = None,
        model: str | None = None,
        default_languages: str = "ko,en",
        deterministic: bool = True,
    ):
        self.llm_client = llm_client
        self.model = model or ""
        self.default_languages = default_languages
        self.deterministic = deterministic

    def extract(self, text: str, ontology: dict[str, Any]) -> dict[str, Any]:
        if not self.llm_client or not self.model:
            raise RuntimeError("provider configuration is required for inline llm extraction")

        normalized_ontology = normalize_ontology(ontology)
        language = _detect_language(text)
        cleaned_text = _clean_document_text_for_llm(text)
        raw_entities_payload = _run_sync(self._extract_entities_with_llm(cleaned_text, normalized_ontology, language))
        entities = _normalize_entities(raw_entities_payload.get("entities", []), cleaned_text, normalized_ontology, language)
        raw_edges_payload = _run_sync(self._extract_edges_with_llm(cleaned_text, normalized_ontology, language, entities))
        edges = _normalize_edges(raw_edges_payload.get("edges", []), entities, normalized_ontology, text, language)

        return {
            "ontology": normalized_ontology,
            "language": language,
            "entities": entities,
            "edges": edges,
            "sentence_count": _sentence_count(text),
            "candidate_count": len(raw_entities_payload.get("entities", [])),
            "typed_entity_count": len(entities),
            "dropped_candidate_count": max(0, len(raw_entities_payload.get("entities", [])) - len(entities)),
        }

    async def _extract_entities_with_llm(self, text: str, ontology: dict[str, Any], language: str) -> dict[str, Any]:
        units = _build_entity_pass_units(text)
        aggregated_entities: list[dict[str, Any]] = []
        for unit_text in units:
            response = await self._create_completion(
                _build_entity_extraction_prompt(unit_text, ontology, language)
            )
            content = response.choices[0].message.content or "{}"
            payload = _parse_json_response(content)
            aggregated_entities.extend(payload.get("entities", []))
        return {"entities": aggregated_entities}

    async def _extract_edges_with_llm(
        self,
        text: str,
        ontology: dict[str, Any],
        language: str,
        entities: list[dict[str, Any]],
    ) -> dict[str, Any]:
        units = _build_edge_pass_units(text, entities)
        if not units:
            response = await self._create_completion(
                _build_edge_extraction_prompt(text, ontology, language, entities)
            )
            content = response.choices[0].message.content or "{}"
            payload = _parse_json_response(content)
            candidate_edges = payload.get("edges", [])
            if not candidate_edges:
                return payload
            recovered_edges = await self._recover_missing_edges_with_llm(
                text=text,
                ontology=ontology,
                language=language,
                entities=entities,
                candidate_edges=candidate_edges,
            )
            candidate_edges = _merge_edge_candidates(recovered_edges, candidate_edges)
            adjudicated_edges = await self._adjudicate_edges_with_llm(
                text=text,
                ontology=ontology,
                language=language,
                entities=entities,
                candidate_edges=candidate_edges,
            )
            candidate_edges = _apply_adjudication_result(candidate_edges, adjudicated_edges)
            consolidated_edges = await self._consolidate_edges_with_llm(
                text=text,
                ontology=ontology,
                language=language,
                entities=entities,
                candidate_edges=candidate_edges,
            )
            if consolidated_edges:
                return {"edges": _merge_edge_candidates(consolidated_edges, candidate_edges)}
            return {"edges": candidate_edges}

        aggregated_edges: list[dict[str, Any]] = []
        for unit_text, unit_entities in units:
            response = await self._create_completion(
                _build_edge_extraction_prompt(unit_text, ontology, language, unit_entities)
            )
            content = response.choices[0].message.content or "{}"
            payload = _parse_json_response(content)
            candidate_edges = payload.get("edges", [])
            if candidate_edges:
                refinement = await self._create_completion(
                    _build_edge_refinement_prompt(unit_text, ontology, language, unit_entities, candidate_edges)
                )
                refinement_content = refinement.choices[0].message.content or "{}"
                refined_payload = _parse_json_response(refinement_content)
                aggregated_edges.extend(refined_payload.get("edges", []))
        if not aggregated_edges:
            return {"edges": []}

        recovered_edges = await self._recover_missing_edges_with_llm(
            text=text,
            ontology=ontology,
            language=language,
            entities=entities,
            candidate_edges=aggregated_edges,
        )
        aggregated_edges = _merge_edge_candidates(recovered_edges, aggregated_edges)
        adjudicated_edges = await self._adjudicate_edges_with_llm(
            text=text,
            ontology=ontology,
            language=language,
            entities=entities,
            candidate_edges=aggregated_edges,
        )
        aggregated_edges = _apply_adjudication_result(aggregated_edges, adjudicated_edges)

        consolidated_edges = await self._consolidate_edges_with_llm(
            text=text,
            ontology=ontology,
            language=language,
            entities=entities,
            candidate_edges=aggregated_edges,
        )
        if consolidated_edges:
            return {"edges": _merge_edge_candidates(consolidated_edges, aggregated_edges)}
        return {"edges": aggregated_edges}

    async def _consolidate_edges_with_llm(
        self,
        text: str,
        ontology: dict[str, Any],
        language: str,
        entities: list[dict[str, Any]],
        candidate_edges: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        try:
            response = await self._create_completion(
                _build_edge_consolidation_prompt(text, ontology, language, entities, candidate_edges)
            )
            content = response.choices[0].message.content or "{}"
            payload = _parse_json_response(content)
        except ValueError:
            return []

        edges = payload.get("edges", [])
        return edges if isinstance(edges, list) else []

    async def _recover_missing_edges_with_llm(
        self,
        text: str,
        ontology: dict[str, Any],
        language: str,
        entities: list[dict[str, Any]],
        candidate_edges: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not candidate_edges:
            return []
        try:
            response = await self._create_completion(
                _build_edge_recovery_prompt(text, ontology, language, entities, candidate_edges)
            )
            content = response.choices[0].message.content or "{}"
            payload = _parse_json_response(content)
        except ValueError:
            return []

        edges = payload.get("edges", [])
        return edges if isinstance(edges, list) else []

    async def _adjudicate_edges_with_llm(
        self,
        text: str,
        ontology: dict[str, Any],
        language: str,
        entities: list[dict[str, Any]],
        candidate_edges: list[dict[str, Any]],
    ) -> list[dict[str, Any]] | None:
        if not candidate_edges:
            return []
        try:
            response = await self._create_completion(
                _build_edge_adjudication_prompt(text, ontology, language, entities, candidate_edges)
            )
            content = response.choices[0].message.content or "{}"
            payload = _parse_json_response(content)
        except ValueError:
            return None

        edges = payload.get("edges", [])
        return edges if isinstance(edges, list) else None

    async def _create_completion(self, prompt: str):
        response = await self.llm_client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an ontology-constrained information extractor. "
                        "Return only valid JSON. Use only the provided entity and edge types. "
                        "Do not invent unsupported types or unsupported relations. "
                        "Prefer exact names as they appear in the text."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            response_format={"type": "json_object"},
        )
        return response


def _build_entity_extraction_prompt(text: str, ontology: dict[str, Any], language: str) -> str:
    entity_lines = []
    for entity in ontology.get("entity_types", []):
        entity_lines.append(
            f"- {entity['name']}: {entity.get('description', '')}".strip()
        )

    return "\n".join(
        [
            f"Document language: {language}",
            "Extract only entities from the text below.",
            'Return JSON with this shape: {"entities":[{"name":"exact text span","type":"AllowedEntityType","aliases":["optional alias"]}]}',
            "Use only the ontology below.",
            "Allowed entity types:",
            *entity_lines,
            "Rules:",
            "- Use only names grounded in the text.",
            "- Keep aliases only when they explicitly appear in the text.",
            "- If uncertain, omit the item.",
            "Text:",
            text,
        ]
    )


def _build_edge_extraction_prompt(
    text: str,
    ontology: dict[str, Any],
    language: str,
    entities: list[dict[str, Any]],
) -> str:
    local_types = {entity["type"] for entity in entities}
    candidate_edges = []
    for edge in ontology.get("edge_types", []):
        allowed_pairs = [
            (pair.get('source', 'Entity'), pair.get('target', 'Entity'))
            for pair in edge.get("source_targets", [])
        ]
        if allowed_pairs and not any(source in local_types and target in local_types for source, target in allowed_pairs):
            continue
        candidate_edges.append(edge)

    edge_lines = []
    for edge in candidate_edges:
        source_targets = ", ".join(
            f"{pair.get('source', 'Entity')}->{pair.get('target', 'Entity')}"
            for pair in edge.get("source_targets", [])
        )
        edge_lines.append(
            f"- {edge['name']}: {edge.get('description', '')} | allowed: {source_targets}"
        )

    entity_lines = [
        f"- {entity['name']} | {entity['type']}"
        for entity in entities
    ] or ["- (no entities extracted)"]

    return "\n".join(
        [
            f"Document language: {language}",
            "Extract only relations from the text below.",
            'Return JSON with this shape: {"edges":[{"name":"ALLOWED_EDGE_NAME","source":"entity name","target":"entity name","fact":"supporting sentence"}]}',
            "You must choose source and target names only from this extracted entity list:",
            *entity_lines,
            "Allowed edge types:",
            *edge_lines,
            "Rules:",
            "- Source and target must be exact entity names from the provided entity list, never type labels.",
            "- Extract all high-confidence relations you can find, not just one.",
            "- Each edge fact must be the shortest supporting sentence or clause, never the whole document.",
            "- Only use edge types from the allowed local edge list below.",
            "- Emit an edge only when the source/target pair matches an allowed signature.",
            "- If uncertain, omit the edge.",
            "Example:",
            '{"edges":[{"name":"PLANS_OPERATION","source":"도널드 트럼프","target":"미군","fact":"도널드 트럼프는 주요 전투 작전 개시를 발표했다."}]}',
            "Text:",
            text,
        ]
    )


def _build_edge_refinement_prompt(
    text: str,
    ontology: dict[str, Any],
    language: str,
    entities: list[dict[str, Any]],
    candidate_edges: list[dict[str, Any]],
) -> str:
    edge_lines = []
    for edge in ontology.get("edge_types", []):
        source_targets = ", ".join(
            f"{pair.get('source', 'Entity')}->{pair.get('target', 'Entity')}"
            for pair in edge.get("source_targets", [])
        )
        edge_lines.append(
            f"- {edge['name']}: {edge.get('description', '')} | allowed: {source_targets}"
        )

    entity_lines = [
        f"- {entity['name']} | {entity['type']}"
        for entity in entities
    ] or ["- (no entities extracted)"]

    return "\n".join(
        [
            f"Document language: {language}",
            "Refine the candidate relations below.",
            'Return JSON with this shape: {"edges":[{"name":"ALLOWED_EDGE_NAME","source":"entity name","target":"entity name","fact":"supporting sentence"}]}',
            "Use only these entity names:",
            *entity_lines,
            "Allowed edge types:",
            *edge_lines,
            "Candidate relations to review:",
            json.dumps(candidate_edges, ensure_ascii=False),
            "Rules:",
            "- Keep only valid high-confidence relations.",
            "- Fix wrong edge names if a better allowed edge type matches the sentence.",
            "- Source and target must be exact entity names from the entity list.",
            "- Fact must be the shortest supporting sentence or clause.",
            "- If a candidate is wrong or unsupported, drop it.",
            "Text:",
            text,
        ]
    )


def _build_edge_consolidation_prompt(
    text: str,
    ontology: dict[str, Any],
    language: str,
    entities: list[dict[str, Any]],
    candidate_edges: list[dict[str, Any]],
) -> str:
    edge_lines = []
    for edge in ontology.get("edge_types", []):
        source_targets = ", ".join(
            f"{pair.get('source', 'Entity')}->{pair.get('target', 'Entity')}"
            for pair in edge.get("source_targets", [])
        )
        edge_lines.append(
            f"- {edge['name']}: {edge.get('description', '')} | allowed: {source_targets}"
        )

    entity_lines = [
        f"- {entity['name']} | {entity['type']}"
        for entity in entities
    ] or ["- (no entities extracted)"]

    return "\n".join(
        [
            f"Document language: {language}",
            "Consolidate the candidate relations below.",
            'Return JSON with this shape: {"edges":[{"name":"ALLOWED_EDGE_NAME","source":"entity name","target":"entity name","fact":"supporting sentence"}]}',
            "Use only these entity names:",
            *entity_lines,
            "Allowed edge types:",
            *edge_lines,
            "Candidate relations gathered from multiple sentence/window passes:",
            json.dumps(candidate_edges, ensure_ascii=False),
            "Rules:",
            "- Review the full text and return the final high-confidence relation set for the document.",
            "- Merge duplicate or overlapping candidate relations into one best edge.",
            "- If a candidate uses the wrong allowed edge type but the fact clearly supports another allowed edge type, correct it.",
            "- Source and target must be exact entity names from the entity list.",
            "- Fact must be the shortest grounded supporting sentence or clause.",
            "- Drop unsupported or low-confidence candidates.",
            "Text:",
            text,
        ]
    )


def _build_edge_recovery_prompt(
    text: str,
    ontology: dict[str, Any],
    language: str,
    entities: list[dict[str, Any]],
    candidate_edges: list[dict[str, Any]],
) -> str:
    edge_lines = []
    for edge in ontology.get("edge_types", []):
        source_targets = ", ".join(
            f"{pair.get('source', 'Entity')}->{pair.get('target', 'Entity')}"
            for pair in edge.get("source_targets", [])
        )
        edge_lines.append(
            f"- {edge['name']}: {edge.get('description', '')} | allowed: {source_targets}"
        )

    entity_lines = [
        f"- {entity['name']} | {entity['type']}"
        for entity in entities
    ] or ["- (no entities extracted)"]

    return "\n".join(
        [
            f"Document language: {language}",
            "Find any additional missing relations in the full text.",
            'Return JSON with this shape: {"edges":[{"name":"ALLOWED_EDGE_NAME","source":"entity name","target":"entity name","fact":"supporting sentence"}]}',
            "Use only these entity names:",
            *entity_lines,
            "Allowed edge types:",
            *edge_lines,
            "Relations already extracted:",
            json.dumps(candidate_edges, ensure_ascii=False),
            "Rules:",
            "- Return only additional high-confidence relations that are missing from the existing set.",
            "- Do not repeat existing relations unless you are correcting a clearly missing edge from another part of the text.",
            "- Source and target must be exact entity names from the entity list.",
            "- Fact must be the shortest grounded supporting sentence or clause.",
            "- If there are no additional missing relations, return an empty edges list.",
            "Text:",
            text,
        ]
    )


def _build_edge_adjudication_prompt(
    text: str,
    ontology: dict[str, Any],
    language: str,
    entities: list[dict[str, Any]],
    candidate_edges: list[dict[str, Any]],
) -> str:
    edge_lines = []
    for edge in ontology.get("edge_types", []):
        source_targets = ", ".join(
            f"{pair.get('source', 'Entity')}->{pair.get('target', 'Entity')}"
            for pair in edge.get("source_targets", [])
        )
        edge_lines.append(
            f"- {edge['name']}: {edge.get('description', '')} | allowed: {source_targets}"
        )

    entity_lines = [
        f"- {entity['name']} | {entity['type']}"
        for entity in entities
    ] or ["- (no entities extracted)"]

    return "\n".join(
        [
            f"Document language: {language}",
            "Adjudicate the candidate relations semantically.",
            'Return JSON with this shape: {"edges":[{"name":"ALLOWED_EDGE_NAME","source":"entity name","target":"entity name","fact":"supporting sentence"}]}',
            "Use only these entity names:",
            *entity_lines,
            "Allowed edge types:",
            *edge_lines,
            "Candidate relations to adjudicate:",
            json.dumps(candidate_edges, ensure_ascii=False),
            "Rules:",
            "- Keep only semantically valid high-confidence relations.",
            "- Drop relations where the chosen source is only a reporter, citation source, or attribution source.",
            "- Drop relations where the fact only names an operation or label without supporting the claimed relation.",
            "- Drop planning relations when the fact only describes an attack already underway and not a plan or announcement.",
            "- Drop impact relations when the target appears only as a reporting source or evidence source.",
            "- Weapon systems or attack types are not valid targets by themselves unless the text explicitly frames them as attacked assets.",
            "- Count or trend sentences should not become attack-target relations.",
            "- Prefer attacked facilities, bases, ships, infrastructure, leaders, or populations over attack-mode labels, rate changes, or statistics.",
            "- You may keep, drop, or correct candidate edges, but do not invent unsupported relations.",
            "- Source and target must remain exact entity names from the entity list.",
            "- Fact must be the shortest grounded supporting sentence or clause.",
            "Text:",
            text,
        ]
    )


def _parse_json_response(content: str) -> dict[str, Any]:
    cleaned = content.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = cleaned.strip()

    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Inline LLM extractor returned invalid JSON: {cleaned[:200]}") from exc

    if not isinstance(payload, dict):
        raise ValueError("Inline LLM extractor returned a non-object payload")
    return payload


def _normalize_entities(
    raw_entities: list[dict[str, Any]],
    text: str,
    ontology: dict[str, Any],
    language: str,
) -> list[dict[str, Any]]:
    allowed_types = {entity["name"] for entity in ontology.get("entity_types", [])}
    merged: list[dict[str, Any]] = []
    resolver = EntityResolver()

    for raw_entity in raw_entities:
        if not isinstance(raw_entity, dict):
            continue
        name = str(raw_entity.get("name", "")).strip()
        entity_type = str(raw_entity.get("type", "")).strip()
        if not name or entity_type not in allowed_types:
            continue

        if resolver.is_generic_title(name):
            continue

        name = resolver.promote_display_name(name)

        aliases = raw_entity.get("aliases", [])
        if isinstance(aliases, str):
            aliases = [aliases]
        aliases = [str(alias).strip() for alias in aliases if str(alias).strip()]

        start, end = _locate_span(text, name)
        payload = {
            "name": name,
            "type": entity_type,
            "attributes": {
                "name": name,
                **({"aliases": sorted(set(aliases))} if aliases else {}),
            },
            "source_span": {
                "start": start,
                "end": end,
                "text": text[start:end] if end > start else name,
            },
            "provenance": {
                "language": language,
                "text": text,
            },
        }

        existing = next(
            (
                item
                for item in merged
                if item["type"] == entity_type
                and resolver.should_merge(
                    {"name": item["name"], "type": item["type"]},
                    {"name": payload["name"], "type": payload["type"]},
                )
            ),
            None,
        )
        if existing is None:
            merged.append(payload)
            continue

        preferred = resolver.preferred_name(existing["name"], payload["name"])
        alias_values = set(existing["attributes"].get("aliases", []))
        alias_values.update(payload["attributes"].get("aliases", []))
        existing["name"] = preferred
        existing["attributes"]["name"] = preferred
        if alias_values:
            existing["attributes"]["aliases"] = sorted(alias_values)

    return merged


def _normalize_edges(
    raw_edges: list[dict[str, Any]],
    entities: list[dict[str, Any]],
    ontology: dict[str, Any],
    text: str,
    language: str,
) -> list[dict[str, Any]]:
    allowed_edges = {
        edge["name"]: {
            (pair.get("source", "Entity"), pair.get("target", "Entity"))
            for pair in edge.get("source_targets", [])
        }
        for edge in ontology.get("edge_types", [])
    }

    entity_lookup = _build_entity_lookup(entities)
    deduped: dict[tuple[str, str, str], dict[str, Any]] = {}
    order: list[tuple[str, str, str]] = []

    for raw_edge in raw_edges:
        if not isinstance(raw_edge, dict):
            continue

        edge_name = _resolve_edge_name(str(raw_edge.get("name", "")).strip(), set(allowed_edges))
        if edge_name is None:
            continue

        fact = str(raw_edge.get("fact", "")).strip() or text
        source = _resolve_edge_endpoint(str(raw_edge.get("source", "")).strip(), entity_lookup, entities, fact)
        target = _resolve_edge_endpoint(str(raw_edge.get("target", "")).strip(), entity_lookup, entities, fact)
        if not source or not target or source["name"] == target["name"]:
            continue

        if allowed_edges[edge_name] and (source["type"], target["type"]) not in allowed_edges[edge_name]:
            continue

        fact = _ground_edge_fact(text, fact, source["name"], target["name"])
        if not _passes_edge_semantic_guard(edge_name, fact, source["name"], target["name"]):
            continue

        source_start, source_end = source["source_span"]["start"], source["source_span"]["end"]
        target_start, target_end = target["source_span"]["start"], target["source_span"]["end"]
        payload = {
            "name": edge_name,
            "source": source["name"],
            "target": target["name"],
            "fact": fact,
            "source_span": {
                "start": min(source_start, target_start),
                "end": max(source_end, target_end),
                "text": fact,
            },
            "provenance": {
                "language": language,
                "text": text,
            },
        }
        key = (edge_name, source["name"], target["name"])
        existing = deduped.get(key)
        if existing is None:
            deduped[key] = payload
            order.append(key)
            continue

        if len(payload["fact"]) < len(existing["fact"]):
            deduped[key] = payload

    return [deduped[key] for key in order]


def _build_entity_lookup(entities: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for entity in entities:
        lookup[_canonical_name(entity["name"])] = entity
        for alias in entity.get("attributes", {}).get("aliases", []):
            lookup[_canonical_name(str(alias))] = entity
    return lookup


def _merge_edge_candidates(preferred_edges: list[dict[str, Any]], fallback_edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not preferred_edges:
        return fallback_edges
    if not fallback_edges:
        return preferred_edges
    return [*preferred_edges, *fallback_edges]


def _apply_adjudication_result(candidate_edges: list[dict[str, Any]], adjudicated_edges: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if adjudicated_edges is None:
        return candidate_edges
    if adjudicated_edges:
        return adjudicated_edges
    if len(candidate_edges) <= 1:
        return adjudicated_edges
    return candidate_edges


def _resolve_entity_name(name: str, lookup: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    if not name:
        return None
    return lookup.get(_canonical_name(name))


def _resolve_edge_endpoint(
    raw_value: str,
    lookup: dict[str, dict[str, Any]],
    entities: list[dict[str, Any]],
    fact: str,
) -> dict[str, Any] | None:
    resolved = _resolve_entity_name(raw_value, lookup)
    if resolved is not None:
        return resolved

    candidates = [entity for entity in entities if entity["type"] == raw_value]
    if not candidates:
        return None

    fact_matches = [entity for entity in candidates if entity["name"] in fact]
    if fact_matches:
        return sorted(fact_matches, key=lambda entity: (-len(entity["name"]), entity["source_span"]["start"]))[0]
    return sorted(candidates, key=lambda entity: (-len(entity["name"]), entity["source_span"]["start"]))[0]


def _normalize_edge_name(value: str) -> str:
    words = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value).replace("-", "_")
    words = re.sub(r"\s+", "_", words)
    return words.upper()


def _resolve_edge_name(value: str, allowed_names: set[str]) -> str | None:
    normalized = _normalize_edge_name(value)
    if normalized in allowed_names:
        return normalized

    candidate_key = normalized.replace("_", "").replace("S", "")
    for allowed in allowed_names:
        allowed_key = allowed.replace("_", "").replace("S", "")
        if candidate_key == allowed_key:
            return allowed
    return None


def _locate_span(text: str, value: str) -> tuple[int, int]:
    start = text.find(value)
    if start < 0:
        return 0, 0
    return start, start + len(value)


def _preferred_name(left: str, right: str) -> str:
    if "(" in right and ")" in right and "(" not in left:
        return right
    if "(" in left and ")" in left and "(" not in right:
        return left
    if _is_acronym(left) and not _is_acronym(right):
        return right
    if _is_acronym(right) and not _is_acronym(left):
        return left
    return right if len(right) > len(left) else left


def _is_acronym(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Z0-9]{2,10}", value))


def _canonical_name(value: str) -> str:
    stripped = re.sub(r"\([A-Z]{2,10}\)", "", value)
    return re.sub(r"[^a-z0-9가-힣]+", "", stripped.lower())


def _sentence_count(text: str) -> int:
    return len(_split_sentences(text))


def _clean_document_text_for_llm(text: str) -> str:
    cleaned_lines = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("==="):
            continue
        if line.startswith("#"):
            continue
        cleaned_lines.append(line.replace("**", ""))
    return "\n".join(cleaned_lines)


def _ground_edge_fact(text: str, fact: str, source_name: str, target_name: str) -> str:
    normalized_fact = " ".join(fact.split())
    if not normalized_fact:
        normalized_fact = " ".join(text.split())

    current_support = _endpoint_support_score(normalized_fact, source_name, target_name)
    if (
        len(normalized_fact) <= 220
        and _sentence_count(normalized_fact) <= 1
        and current_support >= 2
    ):
        return normalized_fact

    best_sentence = _best_supporting_sentence(text, source_name, target_name)
    if not best_sentence:
        return normalized_fact

    best_sentence_support = _endpoint_support_score(best_sentence, source_name, target_name)
    if best_sentence_support < current_support:
        return normalized_fact
    if (
        best_sentence_support == current_support
        and len(normalized_fact) <= 220
        and _sentence_count(normalized_fact) <= 1
    ):
        return normalized_fact

    best_clause = _best_supporting_clause(best_sentence, source_name, target_name)
    best_clause_support = _endpoint_support_score(best_clause, source_name, target_name) if best_clause else -1
    if best_clause_support >= best_sentence_support and best_clause:
        return best_clause
    return best_sentence


def _fact_supports_edge(fact: str, source_name: str, target_name: str) -> bool:
    return _mentions_entity_distinctly(fact, source_name, target_name) and _mentions_entity_distinctly(
        fact, target_name, source_name
    )


def _endpoint_support_score(fact: str, source_name: str, target_name: str) -> int:
    score = 0
    if _mentions_entity_distinctly(fact, source_name, target_name):
        score += 1
    if _mentions_entity_distinctly(fact, target_name, source_name):
        score += 1
    return score


def _passes_edge_semantic_guard(edge_name: str, fact: str, source_name: str, target_name: str) -> bool:
    if edge_name in {"TARGETS", "LAUNCHES_ATTACK_ON", "REPORTS_ON"}:
        return _fact_supports_edge(fact, source_name, target_name)
    return True


def _mentions_entity_distinctly(fact: str, entity_name: str, other_name: str) -> bool:
    fact_key = _canonical_name(fact)
    entity_key = _canonical_name(entity_name)
    other_key = _canonical_name(other_name)
    if not entity_key or entity_key not in fact_key:
        return False
    if other_key and entity_key != other_key and entity_key in other_key:
        return fact_key.count(entity_key) > other_key.count(entity_key)
    return True


def _best_supporting_sentence(text: str, source_name: str, target_name: str) -> str:
    sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+|\n+", text) if sentence.strip()]
    source_key = _canonical_name(source_name)
    target_key = _canonical_name(target_name)
    best_sentence = ""
    best_score = -1

    for sentence in sentences:
        sentence_key = _canonical_name(sentence)
        score = 0
        if source_key and source_key in sentence_key:
            score += 2
        if target_key and target_key in sentence_key:
            score += 2
        if score == 0:
            continue
        if score > best_score or (score == best_score and len(sentence) < len(best_sentence)):
            best_score = score
            best_sentence = sentence

    return " ".join(best_sentence.split())


def _best_supporting_clause(sentence: str, source_name: str, target_name: str) -> str:
    clauses = [clause.strip() for clause in re.split(r"[;,]\s*", sentence) if clause.strip()]
    matches = []
    for clause in clauses:
        normalized_clause = " ".join(clause.split())
        if _fact_supports_edge(normalized_clause, source_name, target_name):
            matches.append(normalized_clause)
    if not matches:
        return ""
    return min(matches, key=len)


def _split_sentences(text: str) -> list[str]:
    return [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+|\n+", text) if sentence.strip()]


def _build_entity_pass_units(text: str) -> list[str]:
    sentences = _split_sentences(text)
    units: list[str] = []
    seen: set[str] = set()

    for index, sentence in enumerate(sentences):
        if len(sentence) < 20 and index + 1 < len(sentences):
            sentence = f"{sentence} {sentences[index + 1]}".strip()
        normalized = " ".join(sentence.split())
        if normalized in seen:
            continue
        units.append(normalized)
        seen.add(normalized)

    return units or [" ".join(text.split())]


def _build_edge_pass_units(text: str, entities: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    sentences = _split_sentences(text)
    units: list[tuple[str, list[dict[str, Any]]]] = []
    seen_texts: set[str] = set()

    for index, sentence in enumerate(sentences):
        local_entities = _entities_in_text(sentence, entities)
        unit_text = sentence
        unit_entities = local_entities

        if len(unit_entities) < 2 and index + 1 < len(sentences):
            candidate_text = f"{sentence} {sentences[index + 1]}".strip()
            candidate_entities = _entities_in_text(candidate_text, entities)
            if len(candidate_entities) >= 2:
                unit_text = candidate_text
                unit_entities = candidate_entities

        if len(unit_entities) < 2:
            continue
        normalized_text = " ".join(unit_text.split())
        if normalized_text in seen_texts:
            continue
        units.append((normalized_text, unit_entities))
        seen_texts.add(normalized_text)

    return units


def _entities_in_text(text: str, entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    found = []
    for entity in entities:
        names = [entity["name"], *(entity.get("attributes", {}).get("aliases", []) or [])]
        if any(name and str(name) in text for name in names):
            found.append(entity)
    return found


def _detect_language(text: str) -> str:
    return "ko" if re.search(r"[가-힣]", text) else "en"


def _run_sync(coro):
    return asyncio.run(coro)

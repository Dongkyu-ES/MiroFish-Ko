# Inline Actual Extractor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rebuild the inline parity extractor so real Korean/English source documents produce non-empty ontology-aligned nodes and a small but useful set of relations.

**Architecture:** Replace the single-regex employment extractor with a deterministic ontology-aware sentence extractor. The new extractor will split text into sentences, generate named-entity candidates, score them against ontology entity types, then infer allowed edges using trigger phrases plus `source_targets` constraints.

**Tech Stack:** Python 3.12, Flask, Graphiti parity engine, `pytest`

---

### Task 1: Lock in real-data expectations with failing tests

**Files:**
- Modify: `backend/tests/parity_engine/test_extractor.py`
- Create: `backend/tests/parity_engine/test_actual_data_extractor.py`
- Reuse: `backend/tests/integration/test_engine_batch_queue.py`

**Step 1: Write the failing test**

Add one unit test that feeds a realistic Korean paragraph and requires non-empty entities and edges:

```python
def test_graphiti_overlay_extracts_entities_and_edges_from_actual_korean_report():
    overlay = GraphitiExtractionOverlay()
    ontology = {...actual-style ontology subset...}
    text = (
        "미국 대통령 도널드 트럼프는 주요 전투 작전 개시를 발표했고, "
        "미군은 이란과 이스라엘을 향한 공습을 수행했다. "
        "국제원자력기구(IAEA)는 나탄즈 농축시설 피해를 보고했다."
    )

    result = overlay.extract(text, ontology)

    assert len(result["entities"]) >= 4
    assert len(result["edges"]) >= 2
```

**Step 2: Add an inline engine persistence test**

Create a test that runs the inline engine path end-to-end and asserts `node_count > 0` and `edge_count > 0` for an actual-data-like chunk.

**Step 3: Run tests to verify failure**

Run:

```bash
/Users/byeongkijeong/miniconda3/envs/kggen/bin/python -m pytest \
  backend/tests/parity_engine/test_extractor.py \
  backend/tests/parity_engine/test_actual_data_extractor.py \
  backend/tests/integration/test_engine_batch_queue.py -q
```

Expected: FAIL because the current extractor only understands `works_for`.

### Task 2: Rebuild entity extraction around ontology-aware candidate scoring

**Files:**
- Modify: `backend/app/parity_engine/extractor.py`
- Optional helper extraction inside same file only

**Step 1: Replace single-pattern logic with sentence pipeline**

Implement these helpers in the same file:
- `_split_sentences(text)`
- `_collect_candidates(sentence)`
- `_score_entity_type(candidate, sentence, entity_type, ontology)`
- `_dedupe_entities(entities)`

**Step 2: Candidate collection rules**

Keep this deterministic and small:
- Korean/English proper-name phrases
- Acronyms in parentheses like `국제원자력기구(IAEA)`
- Country/organization/person title phrases like `미국 대통령 도널드 트럼프`
- Target/infrastructure phrases like `나탄즈 농축시설`, `호르무즈 해협`

**Step 3: Type scoring**

Use ontology-driven scoring, not hard-coded type ids only:
- boost matches from type names, descriptions, examples
- boost common suffixes/titles by semantic family
- choose the best available ontology type per candidate
- drop low-confidence candidates instead of emitting junk

**Step 4: Keep old simple employment tests green**

The new extractor must still satisfy existing `works_for` tests.

### Task 3: Add relation extraction with allowed-signature gating

**Files:**
- Modify: `backend/app/parity_engine/extractor.py`

**Step 1: Implement edge trigger inference**

Add a helper like:

```python
def _extract_edges_from_sentence(sentence, entities, ontology) -> list[dict]:
    ...
```

Use:
- edge name/description keywords
- sentence trigger verbs such as `발표`, `보고`, `규탄`, `촉구`, `공습`, `타격`, `피해`, `공동`, `협력`
- only emit edges whose `(source_type, target_type)` matches ontology `source_targets`

**Step 2: Prefer useful edges over perfect coverage**

Aim for:
- `DECLARES_STATEMENT`
- `REPORTS_ON`
- `TARGETS`
- `LAUNCHES_ATTACK_ON`
- `COORDINATES_WITH`
- `IMPACTS`

Do not try to solve every edge type in one pass.

**Step 3: Ensure edge endpoints exist**

Only emit edges whose `source` and `target` names are both present in extracted entities for the same document.

### Task 4: Add observability for inline extraction quality

**Files:**
- Modify: `backend/app/parity_engine/extractor.py`

**Step 1: Return richer extraction metadata**

Without changing the storage contract, include lightweight metadata in the extractor result:
- `sentence_count`
- `candidate_count`
- `typed_entity_count`
- `dropped_candidate_count`

**Step 2: Log extraction summary in inline persist path**

In `graphiti_client.py`, log counts from inline extraction before persistence.

This is for debugging quality regressions on real documents.

### Task 5: Validate on real-data-like and engine paths

**Files:**
- Test only

**Step 1: Run focused suite**

```bash
/Users/byeongkijeong/miniconda3/envs/kggen/bin/python -m pytest \
  backend/tests/parity_engine/test_extractor.py \
  backend/tests/parity_engine/test_multilingual_extractor.py \
  backend/tests/parity_engine/test_actual_data_extractor.py \
  backend/tests/integration/test_engine_batch_queue.py \
  backend/tests/integration/test_zep_contract_compatibility.py -q
```

**Step 2: Run actual-data smoke**

Use the real project chunk from `proj_3ab636487b4d` under inline mode and verify:
- `node_count > 0`
- `edge_count > 0`
- at least one search query returns facts

**Step 3: Keep scope disciplined**

If this passes, stop. Do not add ML, vector classification, or external NLP dependencies in the same change.

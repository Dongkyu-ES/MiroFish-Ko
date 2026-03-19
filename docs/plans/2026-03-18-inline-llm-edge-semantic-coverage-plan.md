# Inline LLM Edge Semantic Coverage Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reduce obviously wrong inline LLM relations by rejecting edges whose final grounded fact does not independently support the chosen source and target roles.

**Architecture:** Keep extraction fully LLM-based. Preserve the current entity, sentence/window edge, refinement, and final consolidation passes. Add a minimal deterministic validation layer after grounding that checks whether the surviving fact independently mentions both endpoints rather than only containing one endpoint inside the other or omitting the actor entirely.

**Tech Stack:** Python 3.12, OpenAI-compatible async chat completions, Graphiti parity engine, `pytest`

---

### Task 1: Lock the semantic coverage contract with failing tests

**Files:**
- Modify: `backend/tests/parity_engine/test_actual_data_extractor.py`

**Step 1: Add a nested-name false-positive test**

Create a test where:
- source is `이란 해군 선박`
- target is `이란`
- fact only mentions `이란` as part of the source phrase
- final extractor output drops the edge

**Step 2: Add a missing-actor fact test**

Create a test where:
- source is `미 국방 당국`
- target is `주변국`
- fact sentence actually names `이란` as the actor and never mentions the source entity
- final extractor output drops the edge

**Step 3: Run focused tests and verify RED**

Run:

```bash
/Users/byeongkijeong/miniconda3/envs/kggen/bin/python -m pytest \
  backend/tests/parity_engine/test_actual_data_extractor.py::test_graphiti_overlay_drops_edge_when_target_only_appears_inside_source_name \
  backend/tests/parity_engine/test_actual_data_extractor.py::test_graphiti_overlay_drops_edge_when_grounded_fact_omits_source_actor -q
```

Expected: FAIL because the current extractor still accepts these edges.

### Task 2: Add minimal semantic coverage validation

**Files:**
- Modify: `backend/app/parity_engine/extractor.py`

**Step 1: Add endpoint mention helpers**

Add helpers that:
- canonicalize fact text and entity names
- detect whether an entity mention is independent or only present because it is embedded inside the other endpoint name

**Step 2: Apply the coverage gate**

After fact grounding:
- keep the edge only if both source and target are independently supported by the final fact
- keep the logic small and local to edge normalization

**Step 3: Keep clause trimming aligned**

Ensure clause selection does not prefer a clause that loses independent support for one endpoint when the full sentence is better.

### Task 3: Verify regression and real smoke

**Files:**
- No new production files

**Step 1: Run broader parity regression**

```bash
/Users/byeongkijeong/miniconda3/envs/kggen/bin/python -m pytest \
  backend/tests/parity_engine/test_extractor.py \
  backend/tests/parity_engine/test_multilingual_extractor.py \
  backend/tests/parity_engine/test_actual_data_extractor.py \
  backend/tests/parity_engine/test_provider_fail_fast.py \
  backend/tests/integration/test_engine_batch_queue.py \
  backend/tests/parity_engine/test_graphiti_integration.py \
  backend/tests/parity_engine/test_resolution.py \
  backend/tests/parity_engine/test_search.py -q
```

**Step 2: Re-run actual provider smoke**

Use `proj_3ab636487b4d` first chunk and verify:
- `edge_count` stays in the same range as the last successful smoke
- obviously wrong edges such as nested endpoint pairs are reduced
- top search edge for `도널드 트럼프` remains meaningful

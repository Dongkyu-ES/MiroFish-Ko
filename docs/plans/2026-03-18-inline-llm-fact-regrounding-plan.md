# Inline LLM Fact Regrounding Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Recover valid relations that survive extraction but arrive with overly short or partial facts by re-grounding them against the original sentence when the current fact does not support both endpoints well enough.

**Architecture:** Keep extraction and semantic guards as-is. Change only fact grounding. If a candidate fact is short but mentions only one endpoint, do not accept it immediately. Search the original text for a better supporting sentence or clause and prefer that when it provides stronger endpoint coverage.

**Tech Stack:** Python 3.12, OpenAI-compatible async chat completions, Graphiti parity engine, `pytest`

---

### Task 1: Lock the regrounding contract with failing tests

**Files:**
- Modify: `backend/tests/parity_engine/test_actual_data_extractor.py`

**Step 1: Add a failing `PLANS_OPERATION` regrounding test**

Create a test where:
- original text contains a full sentence with `도널드 트럼프` and `미군`
- candidate fact only says `미군은 이를 Operation Epic Fury로 명명했다.`
- final extractor output keeps the edge but upgrades the fact to the fuller supporting sentence

### Task 2: Implement minimal regrounding change

**Files:**
- Modify: `backend/app/parity_engine/extractor.py`

**Step 1: Tighten `_ground_edge_fact(...)` early return**

Only accept the current short fact immediately when it already provides strong endpoint support.

**Step 2: Prefer original sentence when stronger**

If the current fact is short but partial:
- search the original text
- pick the sentence that best covers both endpoints
- keep the existing fallback when no better sentence exists

### Task 3: Verify regression and smoke

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
- `PLANS_OPERATION` can recover when the model returns a clipped naming clause
- top search edge for `도널드 트럼프` becomes meaningful again when such a relation exists

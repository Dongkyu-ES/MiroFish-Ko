# Inline LLM Two-Pass Extraction Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reduce inline LLM extraction instability by switching from one-shot extraction to two-pass extraction: entities first, then edges grounded against the extracted entity list.

**Architecture:** The extractor remains LLM-only, but the prompt/schema becomes two-stage. Pass 1 extracts only entities. After entity normalization and canonicalization, pass 2 extracts only edges and must reference the previously extracted entity names. This reduces type-label edges, generic source/target placeholders, and missing relations caused by one-shot confusion.

**Tech Stack:** Python 3.12, OpenAI-compatible async chat completions, Graphiti parity engine, `pytest`

---

### Task 1: Lock the two-pass contract with failing tests

**Files:**
- Modify: `backend/tests/parity_engine/test_extractor.py`
- Modify: `backend/tests/parity_engine/test_multilingual_extractor.py`
- Modify: `backend/tests/parity_engine/test_actual_data_extractor.py`

**Step 1: Make fake client support response queues**

Allow `_FakeAsyncOpenAI` to return different payloads on successive calls and record messages.

**Step 2: Add a dedicated two-pass assertion**

Add a test that:
- returns entity payload on first call
- returns edge payload on second call
- asserts the fake client was called twice
- asserts final extractor output merges both passes correctly

**Step 3: Update existing extractor tests**

Existing extractor tests should provide:
- pass 1 entity JSON
- pass 2 edge JSON

**Step 4: Run tests to verify failure**

```bash
/Users/byeongkijeong/miniconda3/envs/kggen/bin/python -m pytest \
  backend/tests/parity_engine/test_extractor.py \
  backend/tests/parity_engine/test_multilingual_extractor.py \
  backend/tests/parity_engine/test_actual_data_extractor.py -q
```

Expected: FAIL because the current extractor still does only one LLM call.

### Task 2: Rebuild extractor into entity-pass and edge-pass calls

**Files:**
- Modify: `backend/app/parity_engine/extractor.py`

**Step 1: Split the current LLM call**

Implement:
- `_extract_entities_with_llm(...)`
- `_extract_edges_with_llm(...)`

**Step 2: Entity pass**

Prompt for:
- only `entities`
- exact text-grounded names
- allowed entity types only

Then run existing entity normalization/canonicalization.

**Step 3: Edge pass**

Prompt for:
- only `edges`
- source and target must be chosen from the normalized entity names list
- allowed edge names and allowed source/target signatures only
- sentence-sized `fact`

Then run existing edge normalization and grounding.

### Task 3: Keep validation strict and LLM-only

**Files:**
- Modify: `backend/app/parity_engine/extractor.py`

**Step 1: No rule synthesis**

Do not generate entities or edges locally if the LLM misses them.

**Step 2: Validation rules stay**

Keep:
- allowed entity type filtering
- allowed edge signature filtering
- edge fact grounding
- canonical display name promotion

These remain post-processing, not extraction fallback.

### Task 4: Verify on provider-backed real-data smoke

**Files:**
- No new production files

**Step 1: Run focused suite**

```bash
/Users/byeongkijeong/miniconda3/envs/kggen/bin/python -m pytest \
  backend/tests/parity_engine/test_extractor.py \
  backend/tests/parity_engine/test_multilingual_extractor.py \
  backend/tests/parity_engine/test_actual_data_extractor.py \
  backend/tests/parity_engine/test_provider_fail_fast.py \
  backend/tests/integration/test_engine_batch_queue.py -q
```

**Step 2: Run full regression**

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

**Step 3: Run actual provider inline smoke**

Use `proj_3ab636487b4d` first chunk and verify:
- `node_count > 0`
- `edge_count >= 2`
- `도널드 트럼프` top edge remains meaningful
- canonical display-name improvements remain intact

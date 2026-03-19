# Inline LLM Sentence-Level Edge Pass Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve inline LLM edge recall by running the edge-extraction pass sentence-by-sentence instead of over the whole chunk.

**Architecture:** Keep the two-pass LLM design. Pass 1 still extracts entities from the whole chunk. Pass 2 will iterate over candidate sentences that contain extracted entities, then call the LLM separately for each sentence using only the sentence-local entity list. This keeps extraction LLM-only while reducing context dilution.

**Tech Stack:** Python 3.12, OpenAI-compatible async chat completions, Graphiti parity engine, `pytest`

---

### Task 1: Lock sentence-level behavior with failing tests

**Files:**
- Modify: `backend/tests/parity_engine/test_actual_data_extractor.py`

**Step 1: Add fake LLM queue test**

Add a test where:
- first fake response returns entities
- second fake response returns one edge for sentence 1
- third fake response returns one edge for sentence 2
- extractor should preserve both edges
- fake client call count should be 3

**Step 2: Verify failure**

Run:

```bash
/Users/byeongkijeong/miniconda3/envs/kggen/bin/python -m pytest \
  backend/tests/parity_engine/test_actual_data_extractor.py -q
```

Expected: FAIL because current extractor still performs a single edge pass for the whole chunk.

### Task 2: Add sentence candidate selection

**Files:**
- Modify: `backend/app/parity_engine/extractor.py`

**Step 1: Split document into candidate sentences**

Implement a helper that:
- splits the original text into sentences
- keeps only sentences containing at least two extracted entities or aliases

**Step 2: Build sentence-local entity lists**

For each sentence:
- include only entities actually mentioned in that sentence
- skip sentences without enough local entities to form a valid relation

### Task 3: Run edge LLM pass per sentence

**Files:**
- Modify: `backend/app/parity_engine/extractor.py`

**Step 1: Replace whole-chunk edge pass**

Instead of one `_extract_edges_with_llm(...)` call over the whole text:
- call it once per candidate sentence
- aggregate all returned edges

**Step 2: Keep validation strict**

Continue to apply:
- allowed edge name filtering
- allowed source/target signature filtering
- exact entity-name grounding
- fact sentence/clause grounding

### Task 4: Verify on real provider smoke

**Files:**
- No new production files

**Step 1: Run focused suite**

```bash
/Users/byeongkijeong/miniconda3/envs/kggen/bin/python -m pytest \
  backend/tests/parity_engine/test_actual_data_extractor.py \
  backend/tests/parity_engine/test_extractor.py \
  backend/tests/parity_engine/test_multilingual_extractor.py -q
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

**Step 3: Run actual provider smoke**

Use `proj_3ab636487b4d` first chunk and verify:
- `edge_count >= 2`
- `도널드 트럼프` top edge remains meaningful
- canonical display-name improvements remain intact

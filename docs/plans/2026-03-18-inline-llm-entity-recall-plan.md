# Inline LLM Entity Recall Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the remaining inline LLM bottleneck by improving entity recall and typing before edge extraction runs.

**Architecture:** Keep extraction LLM-only, but stop relying on one chunk-wide entity pass. First clean the text to remove headings/markdown noise, then run entity extraction over sentence/window units and merge the results before the sentence-level edge pass.

**Tech Stack:** Python 3.12, OpenAI-compatible async chat completions, Graphiti parity engine, `pytest`

---

### Task 1: Lock sentence-level entity recall with failing tests

**Files:**
- Modify: `backend/tests/parity_engine/test_actual_data_extractor.py`

**Step 1: Add fake queue test**

Add a test where:
- call 1 returns entities for sentence 1 (`도널드 트럼프`, `미군`)
- call 2 returns entities for sentence 2 (`국제원자력기구(IAEA)`, `나탄즈 농축시설`)
- later edge passes use the merged entity list

Assert the final entity set contains the union across sentences.

**Step 2: Add heading-noise test**

Add a test where raw text includes markdown headings and a document title, and assert cleaned text passed to the LLM does not contain the heading lines.

### Task 2: Introduce text cleaning before LLM calls

**Files:**
- Modify: `backend/app/parity_engine/extractor.py`

**Step 1: Add `_clean_document_text_for_llm()`**

Remove or simplify:
- leading `=== ... ===`
- markdown headings `#`, `##`
- heavy emphasis markers `**`

Keep the narrative content intact.

### Task 3: Switch entity pass to sentence/window aggregation

**Files:**
- Modify: `backend/app/parity_engine/extractor.py`

**Step 1: Split entity extraction into multiple LLM calls**

Build candidate units from cleaned text:
- sentence
- sentence + next sentence when the sentence is too short or obviously dependent

**Step 2: Aggregate entity results**

Collect all entity payloads across calls, then run the existing normalization/canonicalization merge.

**Step 3: Keep LLM-only**

No local entity synthesis. Units are just call boundaries.

### Task 4: Re-run edge pass against richer entity set

**Files:**
- Modify: `backend/app/parity_engine/extractor.py`

No structural change to edge pass beyond consuming the richer merged entity set.

### Task 5: Verify with actual provider smoke

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
- `도널드 트럼프` present
- `미군` present
- `국제원자력기구(IAEA)` present
- `edge_count >= 2`

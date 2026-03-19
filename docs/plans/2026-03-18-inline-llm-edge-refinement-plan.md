# Inline LLM Edge Refinement Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve inline LLM edge quality by adding an LLM refinement pass that adjudicates candidate edges per sentence/window.

**Architecture:** Keep extraction fully LLM-based. Use three stages: sentence/window entity extraction, sentence/window edge candidate extraction, then sentence/window edge refinement. The refinement pass receives the local entity list and candidate edges and returns the final normalized edge set for that sentence/window.

**Tech Stack:** Python 3.12, OpenAI-compatible async chat completions, Graphiti parity engine, `pytest`

---

### Task 1: Lock the refinement contract with failing tests

**Files:**
- Modify: `backend/tests/parity_engine/test_actual_data_extractor.py`

**Step 1: Extend fake client routing**

Allow the fake LLM client to distinguish:
- entity prompts
- edge candidate prompts
- edge refinement prompts

**Step 2: Add a refinement test**

Create a test where:
- edge candidate pass returns one wrong edge type and one noisy fact
- refinement pass returns corrected edge types and shorter facts
- final extractor output reflects the refinement output, not the raw candidate output

### Task 2: Add refinement prompt and pass

**Files:**
- Modify: `backend/app/parity_engine/extractor.py`

**Step 1: Add `_refine_edges_with_llm(...)`**

For each sentence/window with candidate edges:
- pass sentence text
- pass local entity names/types
- pass candidate edges
- ask model to keep only valid, high-confidence edges
- require shortest supporting sentence/clause

**Step 2: Update edge extraction flow**

For each sentence/window:
- candidate extraction call
- refinement call
- aggregate refined edges only

### Task 3: Keep validation strict after refinement

**Files:**
- Modify: `backend/app/parity_engine/extractor.py`

Continue to run:
- edge name normalization
- endpoint resolution
- signature validation
- fact grounding
- dedupe

Refinement should improve quality, not bypass validation.

### Task 4: Verify with real provider smoke

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
- sample edge facts are sentence-sized

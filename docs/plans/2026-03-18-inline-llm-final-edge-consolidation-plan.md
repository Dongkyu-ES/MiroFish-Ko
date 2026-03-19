# Inline LLM Final Edge Consolidation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve inline LLM relation quality by adding a final LLM consolidation pass that deduplicates overlapping sentence/window edges, corrects missing relations that earlier passes mis-typed, and prefers sentence-sized facts.

**Architecture:** Keep extraction fully LLM-based. Preserve the current `entity pass -> sentence/window edge candidate pass -> sentence/window refinement pass` pipeline, then add one final whole-text consolidation prompt that sees the normalized entity set and all refined edge candidates together. Deterministic code remains limited to validation, endpoint resolution, fact grounding, and exact duplicate rejection.

**Tech Stack:** Python 3.12, OpenAI-compatible async chat completions, Graphiti parity engine, `pytest`

---

### Task 1: Lock the final consolidation contract with failing tests

**Files:**
- Modify: `backend/tests/parity_engine/test_actual_data_extractor.py`
- Modify: `backend/tests/parity_engine/test_extractor.py`
- Modify: `backend/tests/parity_engine/test_multilingual_extractor.py`

**Step 1: Extend fake client routing**

Allow the fake LLM client to distinguish:
- entity prompts
- edge candidate prompts
- sentence/window refinement prompts
- final consolidation prompts

**Step 2: Add a failing consolidation test**

Create a test where:
- sentence/window refinement still leaves one wrong or duplicate edge set
- final consolidation returns the corrected deduplicated set
- final extractor output reflects the consolidation result, not the earlier candidate output

**Step 3: Run the focused test and verify RED**

Run:

```bash
/Users/byeongkijeong/miniconda3/envs/kggen/bin/python -m pytest \
  backend/tests/parity_engine/test_actual_data_extractor.py::test_graphiti_overlay_uses_final_consolidation_pass_to_fix_edge_set -q
```

Expected: FAIL because the current extractor does not run a final consolidation prompt.

### Task 2: Add the final consolidation pass

**Files:**
- Modify: `backend/app/parity_engine/extractor.py`

**Step 1: Add a consolidation prompt builder**

Build a full-text prompt that includes:
- normalized entity list
- allowed edge types and signatures
- all refined candidate edges
- instructions to keep only valid high-confidence relations
- instructions to deduplicate and return the shortest grounded fact per surviving relation

**Step 2: Add `_consolidate_edges_with_llm(...)`**

If refined edge candidates exist:
- call the consolidation prompt once on the full text
- return only the consolidation result
- keep the earlier refined candidates as the fallback only if consolidation yields an empty object or malformed empty edge list

**Step 3: Keep validation strict**

Continue to run:
- edge name normalization
- endpoint resolution
- signature validation
- fact grounding
- final deterministic dedupe

### Task 3: Verify focused and broad regression

**Files:**
- No new production files

**Step 1: Run focused extractor suite**

```bash
/Users/byeongkijeong/miniconda3/envs/kggen/bin/python -m pytest \
  backend/tests/parity_engine/test_extractor.py \
  backend/tests/parity_engine/test_multilingual_extractor.py \
  backend/tests/parity_engine/test_actual_data_extractor.py -q
```

**Step 2: Run broader parity regression**

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

### Task 4: Re-run actual provider smoke

**Files:**
- No new production files

Use `proj_3ab636487b4d` first chunk and verify:
- edge count does not regress
- duplicate relation variants are reduced
- top search edge remains meaningful
- sample facts stay sentence-sized

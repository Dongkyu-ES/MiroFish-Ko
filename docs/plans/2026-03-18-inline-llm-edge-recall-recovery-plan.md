# Inline LLM Edge Recall Recovery Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve inline LLM edge recall by adding one whole-text recovery pass that proposes high-confidence missing relations after sentence/window extraction has already run.

**Architecture:** Keep extraction fully LLM-based. Preserve the current entity pass, sentence/window edge pass, refinement pass, consolidation pass, and semantic guards. Add one extra whole-text recovery prompt that sees the entity list, allowed edge types, and already extracted edges, then returns only additional missing relations. Merge the recovery result into the candidate set before final consolidation and validation.

**Tech Stack:** Python 3.12, OpenAI-compatible async chat completions, Graphiti parity engine, `pytest`

---

### Task 1: Lock the recovery contract with failing tests

**Files:**
- Modify: `backend/tests/parity_engine/test_actual_data_extractor.py`
- Modify: `backend/tests/parity_engine/test_extractor.py`
- Modify: `backend/tests/parity_engine/test_multilingual_extractor.py`

**Step 1: Extend fake client routing**

Allow the fake LLM client to distinguish:
- entity prompts
- sentence/window edge prompts
- refinement prompts
- recovery prompts
- consolidation prompts

**Step 2: Add a failing recovery test**

Create a test where:
- sentence/window extraction returns only `TARGETS`
- recovery pass returns missing `PLANS_OPERATION`
- final extractor output keeps both valid edges

### Task 2: Add the whole-text recovery pass

**Files:**
- Modify: `backend/app/parity_engine/extractor.py`

**Step 1: Add a recovery prompt builder**

Build a prompt that includes:
- full cleaned text
- normalized entity list
- allowed edge types and signatures
- already extracted candidate edges
- instruction to return only additional high-confidence relations not already listed

**Step 2: Add `_recover_missing_edges_with_llm(...)`**

After sentence/window refinement:
- call the recovery prompt once
- merge its result with the current candidate edge list
- continue through consolidation and deterministic validation

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
- `도널드 트럼프` 관련 meaningful edge가 다시 나타나는지
- false positives are not reintroduced by recovery

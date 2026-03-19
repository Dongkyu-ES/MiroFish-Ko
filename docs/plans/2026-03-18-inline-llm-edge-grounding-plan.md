# Inline LLM Edge Grounding Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve LLM-only inline extraction so real provider responses yield more grounded edges and shorter sentence-level facts instead of document-sized blobs.

**Architecture:** Keep extraction LLM-only, but tighten the prompt and strengthen post-processing. The model should be instructed to emit multiple high-confidence edges using real entity names, while post-processing trims oversized facts to the best supporting sentence and resolves mild naming mistakes without reverting to rule-based extraction.

**Tech Stack:** Python 3.12, OpenAI-compatible chat completions, Graphiti parity engine, `pytest`

---

### Task 1: Lock edge-grounding expectations with failing tests

**Files:**
- Modify: `backend/tests/parity_engine/test_actual_data_extractor.py`

**Step 1: Add fact-trimming test**

Add a fake-LLM test where:
- the model returns a valid edge
- `fact` is the entire chunk
- expected normalized edge fact is the shortest supporting sentence containing the resolved endpoints

**Step 2: Add multi-edge preservation test**

Add a fake-LLM test where:
- two or three edges are returned
- source/target use exact entity names
- all valid edges survive normalization

**Step 3: Run tests to verify failure**

```bash
/Users/byeongkijeong/miniconda3/envs/kggen/bin/python -m pytest \
  backend/tests/parity_engine/test_actual_data_extractor.py -q
```

Expected: FAIL because current post-processing keeps long fact strings and is too conservative about preserving multiple edges.

### Task 2: Strengthen the LLM extraction prompt

**Files:**
- Modify: `backend/app/parity_engine/extractor.py`

**Step 1: Tighten prompt rules**

Update `_build_extraction_prompt()` to explicitly require:
- source and target must be exact entity names, never type labels
- extract all high-confidence edges, not just one
- each edge fact must be the shortest supporting sentence or clause
- omit uncertain edges instead of guessing

**Step 2: Add light few-shot style guidance**

Without introducing external templates, add one concise inline example in the prompt showing:
- a named source
- a named target
- a short sentence-level fact

### Task 3: Ground edge facts to supporting sentences

**Files:**
- Modify: `backend/app/parity_engine/extractor.py`

**Step 1: Add sentence selector**

Implement a helper that:
- splits the original text into candidate sentences
- scores each sentence for source/target overlap
- returns the shortest strong match

**Step 2: Apply it only as post-processing**

Use it when:
- the LLM fact is too long
- the LLM fact does not clearly include the grounded endpoints
- the LLM fact looks like a whole chunk or multi-paragraph span

This is validation/cleanup, not rule extraction.

### Task 4: Keep edge normalization permissive but bounded

**Files:**
- Modify: `backend/app/parity_engine/extractor.py`

**Step 1: Preserve valid multi-edge output**

Do not collapse distinct edges unless:
- same edge name
- same source
- same target
- same grounded fact

**Step 2: Keep placeholder recovery minimal**

Continue allowing mild recovery for:
- edge-name spelling variants
- source/target type placeholders

Do not add new heuristic relation generation.

### Task 5: Verify with real provider-backed inline smoke

**Files:**
- No new production files

**Step 1: Run focused suite**

```bash
/Users/byeongkijeong/miniconda3/envs/kggen/bin/python -m pytest \
  backend/tests/parity_engine/test_actual_data_extractor.py \
  backend/tests/parity_engine/test_extractor.py \
  backend/tests/parity_engine/test_multilingual_extractor.py \
  backend/tests/parity_engine/test_provider_fail_fast.py \
  backend/tests/integration/test_engine_batch_queue.py -q
```

**Step 2: Run actual-data smoke**

Use `proj_3ab636487b4d` first chunk under real inline provider config and verify:
- `edge_count >= 2`
- top edge fact is sentence-sized, not whole-chunk-sized
- `도널드 트럼프` search returns a meaningful edge

**Step 3: Stop after this**

Do not add heuristic edge synthesis in the same patch.

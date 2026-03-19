# Inline Resolution And Search Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve inline actual-data graph quality by merging acronym/full-form aliases reliably and ranking exact search hits above loose token overlaps.

**Architecture:** Keep the extractor lightweight and deterministic, then strengthen the post-extraction stages. The resolver should understand acronym/full-name pairs and parenthetical aliases, inline persistence should merge duplicates inside the same episode, and search should reward exact phrase matches before generic token overlap.

**Tech Stack:** Python 3.12, Graphiti parity engine, `pytest`

---

### Task 1: Lock alias-merge expectations with failing tests

**Files:**
- Modify: `backend/tests/parity_engine/test_resolution.py`
- Modify: `backend/tests/parity_engine/test_actual_data_extractor.py`
- Modify: `backend/tests/parity_engine/test_graphiti_integration.py`

**Step 1: Add resolver alias tests**

Add tests for:
- `GCC` ↔ `걸프협력회의`
- `IAEA` ↔ `국제원자력기구(IAEA)`
- `EU` ↔ `유럽연합(EU)`

**Step 2: Add inline same-episode merge test**

Add an integration test where one inline episode contains both full-form and acronym references, and assert only one canonical node remains after persistence.

**Step 3: Run tests to verify failure**

```bash
/Users/byeongkijeong/miniconda3/envs/kggen/bin/python -m pytest \
  backend/tests/parity_engine/test_resolution.py \
  backend/tests/parity_engine/test_graphiti_integration.py -q
```

Expected: FAIL because same-episode duplicates are not merged robustly enough.

### Task 2: Strengthen resolver alias logic

**Files:**
- Modify: `backend/app/parity_engine/resolver.py`

**Step 1: Expand canonicalization**

Implement helpers for:
- stripping parenthetical acronyms from full-form names
- extracting acronym tokens from `Full Name (ABC)` style values
- normalizing Korean/English punctuation variants

**Step 2: Improve `should_merge()`**

Merge should succeed when:
- canonical names match
- acronyms match
- one side explicitly contains the other side’s acronym in parentheses

**Step 3: Keep scope narrow**

Do not add fuzzy edit-distance logic in this pass.

### Task 3: Merge duplicates within one inline episode

**Files:**
- Modify: `backend/app/parity_engine/graphiti_client.py`

**Step 1: Reuse resolver during inline persistence**

In `_persist_extraction()`:
- maintain an in-memory `known_nodes` list while iterating extracted entities
- update it after each upsert
- use the resolver against both pre-existing graph nodes and newly created nodes in the same episode

**Step 2: Preserve canonical node choice**

Prefer the richer name:
- if one side is full-form with parenthetical acronym and the other is acronym-only, keep the full-form
- if one side is obvious truncation/noise, keep the cleaner full-form

**Step 3: Verify with tests**

Run the integration tests from Task 1 until same-episode duplicates collapse correctly.

### Task 4: Improve exact-match search ranking

**Files:**
- Modify: `backend/app/parity_engine/search.py`
- Modify: `backend/tests/parity_engine/test_search.py`

**Step 1: Add failing ranking test**

Add a test where:
- one edge contains the exact phrase `도널드 트럼프`
- another edge only overlaps on generic tokens
- the exact phrase result must rank first

**Step 2: Add minimal scoring improvements**

Keep scoring simple:
- exact query substring bonus
- exact candidate name match bonus
- token-overlap score as fallback
- small bonus for candidate types or fields that directly contain the query

**Step 3: Verify no regression**

Run existing search tests plus the new exact-match test.

### Task 5: Real-data inline smoke verification

**Files:**
- No production file changes

**Step 1: Run focused suite**

```bash
/Users/byeongkijeong/miniconda3/envs/kggen/bin/python -m pytest \
  backend/tests/parity_engine/test_resolution.py \
  backend/tests/parity_engine/test_search.py \
  backend/tests/parity_engine/test_actual_data_extractor.py \
  backend/tests/parity_engine/test_graphiti_integration.py \
  backend/tests/integration/test_engine_batch_queue.py \
  backend/tests/integration/test_zep_contract_compatibility.py -q
```

**Step 2: Run actual-data smoke**

Use the first chunk from `proj_3ab636487b4d` under inline mode and verify:
- `걸프협력회의` and `GCC` are not duplicated as separate nodes
- `국제원자력기구(IAEA)` and `IAEA` are not duplicated as separate nodes
- `도널드 트럼프` query returns an exact-match edge near the top

**Step 3: Stop after this**

Do not expand into semantic search, embeddings, or learned ranking in the same patch.

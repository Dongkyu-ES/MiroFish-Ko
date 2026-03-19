# Inline LLM Extractor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the inline parity extractor with an LLM-only ontology-constrained extractor so arbitrary real documents are handled by model reasoning rather than hand-built rules.

**Architecture:** Move extraction responsibility from rule patterns to an OpenAI-compatible JSON extraction prompt. `GraphitiExtractionOverlay` will become a thin LLM wrapper plus validator/post-processor, while `GraphitiEngine` will use the provider bundle LLM client for inline episode ingestion. Tests will stay deterministic by injecting fake LLM responses rather than hitting a network.

**Tech Stack:** Python 3.12, AsyncOpenAI-compatible clients, Graphiti parity engine, `pytest`

---

### Task 1: Lock the new LLM-only contract with failing tests

**Files:**
- Modify: `backend/tests/parity_engine/test_extractor.py`
- Modify: `backend/tests/parity_engine/test_multilingual_extractor.py`
- Modify: `backend/tests/parity_engine/test_actual_data_extractor.py`
- Modify: `backend/tests/integration/test_engine_batch_queue.py`

**Step 1: Replace rule-assumption tests with fake-LLM tests**

Update unit tests so they instantiate `GraphitiExtractionOverlay` with a fake async client returning JSON.

Each fake response should include:
- `entities`: `[{name, type}]`
- `edges`: `[{name, source, target, fact}]`

**Step 2: Add inline-engine fake-LLM persistence test**

Patch the inline extractor or provider call in `test_engine_batch_queue.py` so the inline engine can persist a deterministic fake extraction without any network access.

**Step 3: Run tests to verify failure**

```bash
/Users/byeongkijeong/miniconda3/envs/kggen/bin/python -m pytest \
  backend/tests/parity_engine/test_extractor.py \
  backend/tests/parity_engine/test_multilingual_extractor.py \
  backend/tests/parity_engine/test_actual_data_extractor.py \
  backend/tests/integration/test_engine_batch_queue.py -q
```

Expected: FAIL because the current extractor is still rule-based and does not support fake-LLM injection.

### Task 2: Rebuild `GraphitiExtractionOverlay` as an LLM-only extractor

**Files:**
- Replace: `backend/app/parity_engine/extractor.py`

**Step 1: Constructor**

Make the extractor accept:
- `llm_client`
- `model`
- optional `default_languages`

**Step 2: Extraction flow**

Implement:
- ontology normalization
- prompt builder
- async OpenAI-compatible call
- JSON parser / fence stripping
- entity validation against allowed ontology types
- edge validation against allowed edge names and `source_targets`

**Step 3: Output contract**

Return the same shape used by inline persistence:
- `entities`
- `edges`
- `language`
- `ontology`
- metadata counts

**Step 4: No rule fallback**

If the LLM call fails or returns invalid JSON, raise an error.
Do not silently fall back to regex extraction.

### Task 3: Wire inline engine to use provider-bundle LLM extraction

**Files:**
- Modify: `backend/app/parity_engine/graphiti_client.py`
- Optional: `backend/app/parity_engine/config.py`

**Step 1: Pass provider LLM into extractor**

When `GraphitiEngine` is constructed, initialize the extractor with:
- `self.provider_bundle.llm_client`
- `self.provider_bundle.llm_model`

**Step 2: Provider readiness**

Inline extraction now depends on LLM config too.
Add a narrow readiness check for inline mode:
- require `llm_api_key`
- require `llm_model`

Do not require embedding or rerank just to run inline extraction.

**Step 3: Keep provider-backed Graphiti path unchanged**

The non-inline `graphiti.add_episode(...)` path stays as-is.

### Task 4: Update fail-fast behavior for LLM-only inline mode

**Files:**
- Modify: `backend/tests/parity_engine/test_provider_fail_fast.py`
- Modify: `backend/app/parity_engine/graphiti_client.py`

**Step 1: Add/adjust test**

Add a test proving inline mode also fails fast when no LLM configuration is available.

**Step 2: Implement minimal guard**

Raise a clear runtime error like:
- `"provider configuration is required for inline llm extraction"`

Do not change unrelated readiness endpoints in the same patch unless necessary for correctness.

### Task 5: Real-data smoke with actual provider-backed inline extraction

**Files:**
- No new production files

**Step 1: Run focused suite**

```bash
/Users/byeongkijeong/miniconda3/envs/kggen/bin/python -m pytest \
  backend/tests/parity_engine/test_extractor.py \
  backend/tests/parity_engine/test_multilingual_extractor.py \
  backend/tests/parity_engine/test_actual_data_extractor.py \
  backend/tests/parity_engine/test_provider_fail_fast.py \
  backend/tests/integration/test_engine_batch_queue.py \
  backend/tests/integration/test_zep_contract_compatibility.py -q
```

**Step 2: Run actual-data inline smoke**

Use `proj_3ab636487b4d` first chunk under inline mode with real provider config and verify:
- `node_count > 0`
- `edge_count > 0`
- `도널드 트럼프` query yields a meaningful top edge

**Step 3: Stop after this**

Do not add rule fallback, local NLP packages, or hybrid extraction in the same change.

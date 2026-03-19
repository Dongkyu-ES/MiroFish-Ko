# Provider Episode Retry Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prevent graph builds from failing on transient provider connection errors during provider-backed episode ingestion.

**Architecture:** Keep the current provider-backed ingestion flow, but add bounded retry/backoff inside `GraphitiEngine.process_episode()` before an episode is marked `failed`. Only clearly retryable connection/server errors should retry. Validation and other deterministic errors must still fail immediately. This ensures `GraphBuilderService._wait_for_episodes()` only sees a `failed` episode after retries are exhausted.

**Tech Stack:** Python 3.12, Graphiti parity engine, local_primary HTTP shim, `pytest`

---

### Task 1: Lock retry behavior with failing tests

**Files:**
- Modify: `backend/tests/parity_engine/test_graphiti_integration.py`

**Step 1: Add a retryable provider error test**

Create a test where:
- `GRAPHITI_EPISODE_INLINE=false`
- fake provider-backed `graphiti.add_episode()` raises `RuntimeError("Connection error.")` once, then succeeds

Assert:
- `GraphitiEngine.add_episode()` returns normally
- stored episode status is `processed`
- provider call count is `2`

**Step 2: Run focused test and verify RED**

Run:

```bash
/Users/byeongkijeong/miniconda3/envs/kggen/bin/python -m pytest \
  backend/tests/parity_engine/test_graphiti_integration.py::test_graphiti_engine_retries_retryable_provider_episode_errors -q
```

Expected: FAIL because the current engine marks the episode failed immediately.

### Task 2: Add bounded retry/backoff to provider-backed episodes

**Files:**
- Modify: `backend/app/parity_engine/graphiti_client.py`

**Step 1: Add retry classification helper**

Retry only for:
- connection-like exceptions
- timeout-like exceptions
- HTTP 429 / 5xx when a status code exists
- explicit `Connection error.`-style messages

Do not retry validation errors or ontology contract errors.

**Step 2: Refactor provider-backed episode processing**

Split the existing provider path into a single-attempt helper and wrap it with:
- bounded retry count
- exponential backoff
- final `failed` status only after retries are exhausted

### Task 3: Verify regression and failed-project repro

**Files:**
- No new production files

**Step 1: Run focused parity tests**

```bash
/Users/byeongkijeong/miniconda3/envs/kggen/bin/python -m pytest \
  backend/tests/parity_engine/test_graphiti_integration.py \
  backend/tests/integration/test_zep_contract_compatibility.py \
  backend/tests/integration/test_engine_batch_queue.py -q
```

**Step 2: Re-check the failed-project diagnosis**

Confirm the design now avoids the previous failure mode:
- transient provider connection error does not immediately set episode status to `failed`
- builder no longer aborts early on first transient connection blip

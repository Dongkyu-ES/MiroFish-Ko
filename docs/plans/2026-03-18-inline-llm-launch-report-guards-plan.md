# Inline LLM Launch And Report Guards Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove the next set of remaining inline LLM relation false positives by adding narrow semantic guards for `LAUNCHES_ATTACK_ON` and `REPORTS_ON`.

**Architecture:** Keep extraction fully LLM-based. Preserve all current extraction and normalization stages. Add only two edge-name-specific checks after fact grounding: `LAUNCHES_ATTACK_ON` requires attack language plus grounded endpoint support, and `REPORTS_ON` requires reporting language plus explicit report-target support in the final fact.

**Tech Stack:** Python 3.12, OpenAI-compatible async chat completions, Graphiti parity engine, `pytest`

---

### Task 1: Lock the new guard contract with failing tests

**Files:**
- Modify: `backend/tests/parity_engine/test_actual_data_extractor.py`

**Step 1: Add a failing `LAUNCHES_ATTACK_ON` naming test**

Create a test where:
- source is `미군`
- target is `자폭형(일회성) 드론 공격`
- fact only says the operation was named
- final extractor output drops the edge

**Step 2: Add a failing `REPORTS_ON` missing-target test**

Create a test where:
- source is `로이터`
- target is `도널드 트럼프`
- fact reports casualty numbers but never mentions the target
- final extractor output drops the edge

### Task 2: Add minimal edge-name-specific semantic guards

**Files:**
- Modify: `backend/app/parity_engine/extractor.py`

**Step 1: Add `LAUNCHES_ATTACK_ON` cue validation**

Require:
- attack or strike language
- grounded support for both endpoints

Do not accept naming or labeling sentences as attacks.

**Step 2: Add `REPORTS_ON` target coverage validation**

Require:
- reporting language
- explicit source mention
- explicit target mention in the grounded fact

### Task 3: Verify regression and real smoke

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
- `LAUNCHES_ATTACK_ON` naming false positive disappears
- `REPORTS_ON` missing-target false positive disappears
- `도널드 트럼프` top search edge remains meaningful

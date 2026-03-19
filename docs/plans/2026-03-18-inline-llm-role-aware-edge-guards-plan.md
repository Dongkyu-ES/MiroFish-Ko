# Inline LLM Role-Aware Edge Guards Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reduce remaining inline LLM relation false positives by adding narrow role-aware guards for `PLANS_OPERATION` and `IMPACTS`.

**Architecture:** Keep extraction fully LLM-based. Preserve the current entity, sentence/window edge, refinement, consolidation, and `TARGETS` semantic coverage flow. Add only two edge-name-specific semantic validators after fact grounding: `PLANS_OPERATION` requires planning or announcement language, and `IMPACTS` rejects cases where the target appears only as a reporting or citation source.

**Tech Stack:** Python 3.12, OpenAI-compatible async chat completions, Graphiti parity engine, `pytest`

---

### Task 1: Lock the role-aware guard contract with failing tests

**Files:**
- Modify: `backend/tests/parity_engine/test_actual_data_extractor.py`

**Step 1: Add a failing `PLANS_OPERATION` test**

Create a test where:
- source is `미국`
- target is `이스라엘`
- fact says the war started with a joint strike
- there is no planning or announcement cue
- final extractor output drops the edge

**Step 2: Add a failing `IMPACTS` reporting-source test**

Create a test where:
- source is `이란`
- target is `적신월사(IRCS)`
- fact mentions the target only as the source of casualty figures
- final extractor output drops the edge

**Step 3: Run the focused tests and verify RED**

Run:

```bash
/Users/byeongkijeong/miniconda3/envs/kggen/bin/python -m pytest \
  backend/tests/parity_engine/test_actual_data_extractor.py::test_graphiti_overlay_drops_plans_operation_without_planning_or_announcement_cue \
  backend/tests/parity_engine/test_actual_data_extractor.py::test_graphiti_overlay_drops_impacts_edge_when_target_is_only_reporting_source -q
```

Expected: FAIL because the current extractor still accepts both edges.

### Task 2: Add minimal edge-name-specific semantic guards

**Files:**
- Modify: `backend/app/parity_engine/extractor.py`

**Step 1: Add `PLANS_OPERATION` cue validation**

Require the grounded fact to contain an explicit planning or announcement cue such as:
- 발표
- 성명
- 계획
- 지시
- 명령
- announce / plan / order

Do not treat generic attack-start wording alone as enough.

**Step 2: Add `IMPACTS` reporting-source rejection**

Reject `IMPACTS` when:
- the target is mentioned only in reporting context
- examples include `수치`, `통계`, `집계`, `근거로`, `인용`, `브리핑`, `according to`, `citing`

Keep the logic local to edge normalization and avoid broad cross-edge rules.

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
- `PLANS_OPERATION(미국 -> 이스라엘)` disappears
- `IMPACTS(이란 -> 적신월사(IRCS))` disappears
- `도널드 트럼프` top search edge remains meaningful

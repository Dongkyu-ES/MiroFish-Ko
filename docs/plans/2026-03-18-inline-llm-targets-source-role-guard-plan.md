# Inline LLM Targets Source Role Guard Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove remaining `TARGETS` false positives where the chosen source is not the attacker but only appears as a reporting or attribution source.

**Architecture:** Keep extraction fully LLM-based. Preserve the current edge recovery, consolidation, semantic guards, and regrounding flow. Add one narrow `TARGETS` source-role check after fact grounding: if the chosen source appears only in a reporting preamble such as `...에 따르면`, reject the edge.

**Tech Stack:** Python 3.12, OpenAI-compatible async chat completions, Graphiti parity engine, `pytest`

---

### Task 1: Lock the source-role contract with a failing test

**Files:**
- Modify: `backend/tests/parity_engine/test_actual_data_extractor.py`

**Step 1: Add a failing reporting-preamble source test**

Create a test where:
- source is `미 국방 당국`
- target is `역내 미군 거점`
- fact says `미 국방 당국과 다수 보도에 따르면 ... 이란은 ... 보복 타격으로 대응했다`
- final extractor output drops the edge

**Step 2: Run the focused test and verify RED**

Run:

```bash
/Users/byeongkijeong/miniconda3/envs/kggen/bin/python -m pytest \
  backend/tests/parity_engine/test_actual_data_extractor.py::test_graphiti_overlay_drops_targets_edge_when_source_is_only_reporting_preamble -q
```

Expected: FAIL because the current extractor still accepts this edge.

### Task 2: Add a narrow `TARGETS` source-role guard

**Files:**
- Modify: `backend/app/parity_engine/extractor.py`

**Step 1: Add reporting-context detection for the source**

Detect patterns where the selected source appears only in a reporting/attribution phrase, for example:
- `X에 따르면`
- `X과 다수 보도에 따르면`
- `according to X`

**Step 2: Apply only to `TARGETS`**

Keep the check local to `TARGETS` semantic validation so unrelated edge types are untouched.

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
- `미 국방 당국 -> 역내 미군 거점` false positive disappears
- `도널드 트럼프 -> 미군` meaningful edge still survives when present

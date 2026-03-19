# Inline LLM Target Role Prompt Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reduce remaining weapon-event and statistical-trend target false positives by making the semantic adjudication prompt explicitly reject them.

**Architecture:** Keep the current LLM-first extraction pipeline. Do not add new deterministic rules. Strengthen only the adjudication prompt so the model distinguishes real attacked assets from attack types, weapon-event labels, counts, and trend sentences.

**Tech Stack:** Python 3.12, OpenAI-compatible async chat completions, Graphiti parity engine, `pytest`

---

### Task 1: Lock the prompt contract with a failing test

**Files:**
- Modify: `backend/tests/parity_engine/test_extractor.py`

**Step 1: Add a prompt contract test**

Import the adjudication prompt builder and assert the generated prompt explicitly says:
- weapon systems or attack types are not valid targets by themselves
- statistical trend or count sentences should not be converted into attack-target edges

**Step 2: Run the focused test and verify RED**

Run:

```bash
/Users/byeongkijeong/miniconda3/envs/kggen/bin/python -m pytest \
  backend/tests/parity_engine/test_extractor.py::test_edge_adjudication_prompt_rejects_weapon_event_targets_and_stat_trends -q
```

Expected: FAIL because the current prompt does not yet state this rule.

### Task 2: Strengthen the adjudication prompt

**Files:**
- Modify: `backend/app/parity_engine/extractor.py`

**Step 1: Add explicit target-role rules**

In the adjudication prompt, state that:
- attack modes, weapon labels, or event names are not valid `TARGETS`/`LAUNCHES_ATTACK_ON` targets unless the text explicitly frames them as attacked assets
- count or trend sentences such as decrease/increase/rate summaries should not produce attack-target relations
- prefer facilities, bases, ships, infrastructure, leaders, or populations when the text actually says they were attacked or impacted

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
- `자폭형(일회성) 드론 공격`, `탄도미사일 공격` 같은 target 오판이 줄어드는지
- `도널드 트럼프 -> 미군` meaningful edge가 유지되는지

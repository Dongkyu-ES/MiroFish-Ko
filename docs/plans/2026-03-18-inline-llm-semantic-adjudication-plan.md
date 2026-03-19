# Inline LLM Semantic Adjudication Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Shift false-positive filtering back toward an LLM-first pipeline by replacing most edge-type-specific semantic rules with a dedicated whole-text semantic adjudication pass.

**Architecture:** Keep extraction fully LLM-based. Preserve the current entity pass, sentence/window edge pass, refinement pass, recovery pass, consolidation pass, and minimal factual grounding. Add one semantic adjudication prompt over the full text and candidate edge set. Use deterministic code only for structural validation such as type/signature checks, endpoint resolution, and minimal endpoint mention support where required.

**Tech Stack:** Python 3.12, OpenAI-compatible async chat completions, Graphiti parity engine, `pytest`

---

### Task 1: Lock the adjudication contract with failing tests

**Files:**
- Modify: `backend/tests/parity_engine/test_extractor.py`
- Modify: `backend/tests/parity_engine/test_multilingual_extractor.py`
- Modify: `backend/tests/parity_engine/test_actual_data_extractor.py`

**Step 1: Extend fake client routing**

Allow the fake LLM client to distinguish:
- entity prompts
- edge prompts
- refinement prompts
- recovery prompts
- semantic adjudication prompts
- consolidation prompts

**Step 2: Add a failing adjudication-pass test**

Create a test where:
- sentence/window extraction yields one valid `TARGETS` edge and one false `PLANS_OPERATION`
- adjudication returns only the valid semantic set
- final extractor output reflects the adjudicated result
- prompt routing proves the adjudication pass ran

### Task 2: Add semantic adjudication and simplify deterministic rules

**Files:**
- Modify: `backend/app/parity_engine/extractor.py`

**Step 1: Add an adjudication prompt builder**

The prompt should:
- see the full text
- see the normalized entity list
- see allowed edge types and signatures
- see the current candidate edge set
- keep valid edges
- drop semantic false positives such as reporting-source attackers, naming-only attack facts, planning-vs-executed confusion, and reporting-source impact targets

**Step 2: Add `_adjudicate_edges_with_llm(...)`**

Run the adjudication pass after recovery and before consolidation.

**Step 3: Reduce deterministic semantic rules**

Keep only minimal deterministic checks:
- endpoint/signature resolution
- minimal endpoint mention support where structurally necessary

Move nuanced semantic rejection back to the LLM adjudication pass.

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
- `도널드 트럼프 -> 미군` meaningful edge still appears
- obvious false positives are still suppressed
- the remaining pipeline is mostly LLM-driven, with deterministic code limited to grounding and schema validation

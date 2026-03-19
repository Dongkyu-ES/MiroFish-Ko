# Canonical Display Name Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make LLM-based inline extraction choose stable, human-usable canonical display names instead of acronyms, overlong titles, or generic document spans.

**Architecture:** Keep extraction LLM-only, but centralize name preference in the resolver. The resolver will score display-name quality, and both extractor entity merge and inline persistence will use the same canonical-name chooser.

**Tech Stack:** Python 3.12, Graphiti parity engine, `pytest`

---

### Task 1: Lock canonical-name expectations with failing tests

**Files:**
- Modify: `backend/tests/parity_engine/test_resolution.py`
- Modify: `backend/tests/parity_engine/test_actual_data_extractor.py`
- Modify: `backend/tests/parity_engine/test_graphiti_integration.py`

**Step 1: Add resolver preference tests**

Cover cases like:
- `GCC` vs `걸프협력회의(GCC)` -> prefer full-form with acronym
- `도널드 트럼프` vs `미국 대통령 도널드 트럼프` -> prefer shorter person name
- `2026년 이란~미국 전쟁 심층 연대기 보고서` vs real organization/person names -> prefer non-title entity names

**Step 2: Add inline integration test**

Use a fake inline extraction with duplicate entity names of different quality and assert the persisted node keeps the best display name.

### Task 2: Implement display-name scoring in resolver

**Files:**
- Modify: `backend/app/parity_engine/resolver.py`

**Step 1: Add a display-name scoring helper**

Score names higher when they are:
- full-form + parenthetical acronym
- clear organization names
- clean person names without titles

Score names lower when they are:
- acronym-only
- document titles
- obviously generic spans (`보고서`, `요약`, `문서`, `성명` as standalone titles)
- title-heavy person strings when a shorter person alias exists

**Step 2: Route `preferred_name()` through this scoring**

Use the quality score first, then length as tiebreaker.

### Task 3: Reuse canonical-name preference everywhere

**Files:**
- Modify: `backend/app/parity_engine/extractor.py`
- Modify: `backend/app/parity_engine/graphiti_client.py`

**Step 1: Extractor merge**

When `_normalize_entities()` merges duplicates, use resolver preference logic rather than local ad-hoc selection.

**Step 2: Inline persistence merge**

When `_persist_extraction()` merges against existing nodes, keep the higher-quality display name rather than the last/longest string.

### Task 4: Validate on actual-data-like and real provider smoke

**Files:**
- No new production files

**Step 1: Run focused suite**

```bash
/Users/byeongkijeong/miniconda3/envs/kggen/bin/python -m pytest \
  backend/tests/parity_engine/test_resolution.py \
  backend/tests/parity_engine/test_actual_data_extractor.py \
  backend/tests/parity_engine/test_graphiti_integration.py -q
```

**Step 2: Run real provider inline smoke**

Use the first chunk of `proj_3ab636487b4d` and verify:
- `걸프협력회의(GCC)` survives instead of `GCC`
- `국제원자력기구(IAEA)` survives instead of `IAEA`
- `도널드 트럼프` survives instead of `미국 대통령 도널드 트럼프`
- document title is not chosen as a canonical entity name

# Canonical Display Name Polish Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Polish canonical display names so inline LLM extraction emits stable, human-usable names with consistent parenthetical aliases and without quantity/title noise.

**Architecture:** Keep extraction LLM-only and continue treating naming as post-processing. Extend resolver display-name promotion so full-form known organizations gain canonical parenthetical aliases, and quantity/title-heavy strings are collapsed to cleaner names before merge/persistence.

**Tech Stack:** Python 3.12, Graphiti parity engine, `pytest`

---

### Task 1: Lock remaining naming defects with failing tests

**Files:**
- Modify: `backend/tests/parity_engine/test_resolution.py`
- Modify: `backend/tests/parity_engine/test_actual_data_extractor.py`
- Modify: `backend/tests/parity_engine/test_graphiti_integration.py`

**Step 1: Add resolver-level tests**

Cover:
- `promote_display_name("유럽연합") -> "유럽연합(EU)"`
- `promote_display_name("걸프협력회의") -> "걸프협력회의(GCC)"`
- `promote_display_name("국제원자력기구") -> "국제원자력기구(IAEA)"`
- `promote_display_name("이란 해군 선박 50척 이상") -> "이란 해군 선박"`
- `promote_display_name("이란 최고지도자 알리 하메네이") -> "알리 하메네이"`

**Step 2: Add extractor-level tests**

Cover:
- plain full-form org names are promoted to parenthetical canonical forms
- quantity-heavy names are normalized before merge

**Step 3: Add inline integration test**

Use fake inline extraction payloads that contain:
- `유럽연합`
- `걸프협력회의`
- `이란 해군 선박 50척 이상`
- `이란 최고지도자 알리 하메네이`

Assert persisted node names are the cleaned canonical forms.

### Task 2: Extend resolver display-name promotion

**Files:**
- Modify: `backend/app/parity_engine/resolver.py`

**Step 1: Parenthetical alias completion**

If a value is already a known full-form alias without parentheses, promote it to:
- `유럽연합(EU)`
- `걸프협력회의(GCC)`
- `국제원자력기구(IAEA)`
- similar known org cases

**Step 2: Quantity suffix cleanup**

Trim trailing quantity expressions such as:
- `50척 이상`
- `5,000개 이상`
- `140명`

Only when they are clearly descriptive counts, not core names.

**Step 3: Title-heavy person cleanup**

When a name begins with person titles like:
- `미국 대통령`
- `이란 최고지도자`

collapse it to the person core name if the remainder still looks like a person name.

### Task 3: Reuse the same promotion everywhere

**Files:**
- Modify: `backend/app/parity_engine/extractor.py`
- Modify: `backend/app/parity_engine/graphiti_client.py` only if needed

**Step 1: Extractor entity normalization**

Call resolver promotion before canonical merge so raw LLM names are cleaned consistently.

**Step 2: Inline persistence**

If any direct persistence path still prefers pre-promotion names, route it through the same resolver helper.

### Task 4: Verify with provider-backed real-data smoke

**Files:**
- No new production files

**Step 1: Run focused suite**

```bash
/Users/byeongkijeong/miniconda3/envs/kggen/bin/python -m pytest \
  backend/tests/parity_engine/test_resolution.py \
  backend/tests/parity_engine/test_actual_data_extractor.py \
  backend/tests/parity_engine/test_graphiti_integration.py -q
```

**Step 2: Run actual provider smoke**

Use `proj_3ab636487b4d` first chunk and verify:
- `유럽연합(EU)` present, `유럽연합` absent
- `걸프협력회의(GCC)` present, `GCC` absent
- `국제원자력기구(IAEA)` present
- `도널드 트럼프` present, titled variant absent
- document title absent
- quantity-heavy military names normalized

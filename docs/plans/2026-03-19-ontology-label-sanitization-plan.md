# Ontology Label Sanitization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prevent Graphiti/Zep graph builds from failing when generated ontology type names include instructional suffixes like `(영문 PascalCase)` or `(영문 UPPER_SNAKE_CASE)`.

**Architecture:** Fix both the source and the sink. First, remove the misleading instructional suffixes from the ontology-generation prompt examples so new ontologies are generated correctly. Second, sanitize existing malformed ontologies during normalization so provider-backed graph builds use Graphiti-safe entity labels and edge names even when older projects already contain bad names.

**Tech Stack:** Python 3.12, Graphiti parity engine, ontology generator service, `pytest`

---

### Task 1: Lock the sanitization contract with failing tests

**Files:**
- Modify: `backend/tests/parity_engine/test_graphiti_ontology_adapter.py`
- Create or Modify: `backend/tests/services/test_ontology_generator.py`

**Step 1: Add an ontology adapter sanitization test**

Create a test where:
- entity type names contain ` (영문 PascalCase)`
- edge names contain ` (영문 UPPER_SNAKE_CASE)`
- source_targets reference the unsanitized entity names

Assert:
- Graphiti config entity keys are sanitized
- edge type names are sanitized
- edge_type_map uses sanitized source/target names

**Step 2: Add an ontology generator post-process test**

Create a test where `_validate_and_process()` receives names with the same instructional suffixes.

Assert:
- stored `entity_types[].name` values are sanitized
- stored `edge_types[].name` values are sanitized
- `source_targets` are rewritten to match the sanitized entity names

**Step 3: Run focused tests and verify RED**

### Task 2: Fix prompt and normalization

**Files:**
- Modify: `backend/app/services/ontology_generator.py`
- Modify: `backend/app/parity_engine/ontology.py`

**Step 1: Fix ontology generator prompt examples**

Change the JSON example so the `name` fields contain only the actual identifier values, not explanatory suffixes.

**Step 2: Sanitize malformed names in generator post-processing**

During `_validate_and_process()`:
- strip known instructional suffixes
- normalize edge names to clean UPPER_SNAKE_CASE values
- rewrite source_targets to match sanitized entity names

**Step 3: Sanitize malformed names in parity ontology normalization**

During `normalize_ontology()`:
- sanitize entity type names to Graphiti-safe labels
- sanitize edge names
- rewrite source_targets with sanitized entity names

### Task 3: Verify regression and project repro

**Files:**
- No new production files

**Step 1: Run focused tests**

```bash
/Users/byeongkijeong/miniconda3/envs/kggen/bin/python -m pytest \
  backend/tests/parity_engine/test_graphiti_ontology_adapter.py \
  backend/tests/services/test_ontology_generator.py -q
```

**Step 2: Run broader regression**

```bash
/Users/byeongkijeong/miniconda3/envs/kggen/bin/python -m pytest \
  backend/tests/parity_engine/test_graphiti_ontology_adapter.py \
  backend/tests/parity_engine/test_graphiti_integration.py \
  backend/tests/services/test_ontology_generator.py -q
```

**Step 3: Re-check the failed project ontology**

Use `proj_332b843e6f89` stored ontology and verify the normalized entity labels no longer contain spaces/parenthetical hints that violate Graphiti label rules.

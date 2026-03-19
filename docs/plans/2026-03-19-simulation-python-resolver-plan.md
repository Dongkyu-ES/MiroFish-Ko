# Simulation Python Resolver Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prevent simulation subprocesses from launching with a broken Python interpreter that cannot import `sqlite3`.

**Architecture:** Keep the current subprocess-based simulation runner, but stop assuming `sys.executable` is healthy. Add a small resolver in `SimulationRunner` that:
- prefers an explicit env override when provided
- otherwise uses the current interpreter if it can import `sqlite3`
- otherwise falls back to a healthy known environment interpreter

The resolver should validate candidates before use and fail with a clear error if no healthy Python is available.

**Tech Stack:** Python 3.12, subprocess-based simulation runner, `pytest`

---

### Task 1: Lock resolver behavior with failing tests

**Files:**
- Create: `backend/tests/services/test_simulation_runner.py`

**Step 1: Add a fallback selection test**

Create a test where:
- `sys.executable` is unhealthy
- a fallback candidate is healthy

Assert:
- resolver returns the healthy fallback path

**Step 2: Add an override preference test**

Create a test where:
- `SIMULATION_PYTHON_EXECUTABLE` is set
- override path is healthy

Assert:
- resolver returns the override path first

### Task 2: Add resolver and health check

**Files:**
- Modify: `backend/app/services/simulation_runner.py`

**Step 1: Add `_python_supports_sqlite(...)`**

Validate a Python interpreter by running a tiny `import sqlite3` subprocess.

**Step 2: Add `_resolve_python_executable()`**

Search in this order:
- `SIMULATION_PYTHON_EXECUTABLE`
- current `sys.executable`
- likely local conda env interpreters such as `kggen`

**Step 3: Use the resolver in subprocess launch**

Replace the raw `sys.executable` command with the resolved healthy interpreter.

### Task 3: Verify regression and local repro

**Files:**
- No new production files

**Step 1: Run focused tests**

```bash
/Users/byeongkijeong/miniconda3/envs/kggen/bin/python -m pytest \
  backend/tests/services/test_simulation_runner.py -q
```

**Step 2: Re-check the broken interpreter diagnosis**

Confirm:
- `/Users/byeongkijeong/miniconda3/bin/python` fails `import sqlite3`
- resolver would choose `/Users/byeongkijeong/miniconda3/envs/kggen/bin/python`

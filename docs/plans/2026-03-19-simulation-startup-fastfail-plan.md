# Simulation Startup Fast-Fail Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Stop simulation starts from reporting success when the chosen Python interpreter is missing required runtime dependencies or when the child process dies immediately after launch.

**Architecture:** Keep the subprocess-based runner. Strengthen interpreter health checks so a candidate Python must import `sqlite3`, `camel`, and `oasis`, not just `sqlite3`. Then add a short startup verification window after `subprocess.Popen` so the runner notices immediate child failure and returns a failed state instead of announcing a successful start.

**Tech Stack:** Python 3.12, subprocess-based simulation runner, `pytest`

---

### Task 1: Lock behavior with failing tests

**Files:**
- Modify: `backend/tests/services/test_simulation_runner.py`

**Step 1: Add dependency-aware resolver test**

Create a test where:
- current interpreter passes `sqlite3` only
- fallback interpreter passes all required imports

Assert:
- resolver chooses the fallback interpreter

**Step 2: Add immediate child-exit startup test**

Create a test where:
- `subprocess.Popen` returns a fake process that exits immediately with a non-zero code
- `simulation.log` already contains an error message

Assert:
- `start_simulation()` returns/records `FAILED`
- state error includes log context
- process is not kept as a running simulation

### Task 2: Implement dependency-aware resolver and startup fast-fail

**Files:**
- Modify: `backend/app/services/simulation_runner.py`

**Step 1: Expand Python health check**

Require candidate interpreters to import:
- `sqlite3`
- `camel`
- `oasis`

**Step 2: Add startup verification**

After `Popen`:
- wait briefly for immediate exit
- if the process exits early, read a short tail from `simulation.log`
- mark the run state failed and do not report `RUNNING`

### Task 3: Verify regression and local repro

**Files:**
- No new production files

**Step 1: Run focused tests**

```bash
/Users/byeongkijeong/miniconda3/envs/kggen/bin/python -m pytest \
  backend/tests/services/test_simulation_runner.py -q
```

**Step 2: Re-check interpreter diagnosis**

Confirm:
- base Python fails one or more required imports
- selected fallback Python passes all required imports

**Step 3: Re-check failed simulation symptom**

Confirm a start attempt no longer stays in a fake “started but frozen” state when the child process dies immediately.

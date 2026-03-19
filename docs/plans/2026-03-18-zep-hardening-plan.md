# Zep Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove the remaining silent-failure and low-recall gaps in the Zep/MiroFish integration so runtime behavior matches Zep contracts more closely.

**Architecture:** Tighten the Zep boundary instead of adding more heuristics. Remote Zep modes should fail loudly on contract/configuration errors, polling paths should distinguish transient errors from permanent ones, and profile enrichment should query Zep with multiple focused queries instead of one vague string.

**Tech Stack:** Python 3.12, Flask, `zep_cloud`, local Zep shim for `local_primary`, `pytest`

---

### Task 1: Harden `search_graph()` against silent remote fallback

**Files:**
- Modify: `backend/app/services/zep_tools.py`
- Create or Modify: `backend/tests/integration/test_zep_search_contract_guards.py`
- Re-run: `backend/tests/integration/test_zep_contract_compatibility.py`

**Step 1: Write the failing test**

Add a test proving that remote Zep modes do not silently fall back to `_local_search()` on permanent search errors.

```python
def test_search_graph_raises_on_remote_contract_error(monkeypatch):
    import backend.app.services.zep_tools as zep_tools_module

    class PermanentSearchError(Exception):
        status_code = 400

    service = zep_tools_module.ZepToolsService(api_key="dummy")
    service.client = SimpleNamespace(
        graph=SimpleNamespace(
            search=lambda **kwargs: (_ for _ in ()).throw(PermanentSearchError("bad request"))
        )
    )
    monkeypatch.setattr(zep_tools_module.Config, "GRAPH_BACKEND", "zep")

    with pytest.raises(PermanentSearchError):
        service.search_graph("graph-1", "alice employer")
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest backend/tests/integration/test_zep_search_contract_guards.py -q`

Expected: FAIL because `search_graph()` currently catches every exception and calls `_local_search()`.

**Step 3: Write minimal implementation**

In `backend/app/services/zep_tools.py`:
- Add a small helper like `_should_fallback_to_local_search(error)` or `_is_remote_permanent_error(error)`.
- Allow `_local_search()` only when:
  - `Config.GRAPH_BACKEND == "local_primary"`, or
  - the exception is clearly transient and an explicit degraded-mode fallback is intended.
- Re-raise permanent remote errors in `zep` and `shadow_eval`.
- Keep the implementation narrow; do not refactor unrelated search formatting.

**Step 4: Run focused tests**

Run:
- `PYTHONPATH=. pytest backend/tests/integration/test_zep_search_contract_guards.py -q`
- `PYTHONPATH=. pytest backend/tests/integration/test_zep_contract_compatibility.py -q`

Expected: PASS. Remote contract errors should surface; existing compatibility tests should remain green.

**Step 5: Optional checkpoint commit**

```bash
git add backend/app/services/zep_tools.py backend/tests/integration/test_zep_search_contract_guards.py
git commit -m "fix: stop silent local fallback for remote zep search errors"
```

### Task 2: Stop swallowing polling errors in graph build

**Files:**
- Modify: `backend/app/services/graph_builder.py`
- Modify: `backend/tests/integration/test_zep_runtime_contracts.py`

**Step 1: Write the failing test**

Add a test proving that permanent polling errors fail fast instead of waiting until timeout.

```python
def test_wait_for_episodes_raises_on_permanent_poll_error():
    builder = object.__new__(GraphBuilderService)

    class PermanentEpisodeError(Exception):
        status_code = 404

    builder.client = SimpleNamespace(
        graph=SimpleNamespace(
            episode=SimpleNamespace(
                get=lambda uuid_: (_ for _ in ()).throw(PermanentEpisodeError("not found"))
            )
        )
    )

    with pytest.raises(PermanentEpisodeError):
        builder._wait_for_episodes(["ep-1"], timeout=1)
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest backend/tests/integration/test_zep_runtime_contracts.py -q`

Expected: FAIL because `_wait_for_episodes()` currently ignores non-`RuntimeError` exceptions during polling.

**Step 3: Write minimal implementation**

In `backend/app/services/graph_builder.py`:
- Add a helper to classify polling errors as transient vs permanent.
- Re-raise permanent errors immediately.
- Optionally keep a small transient-failure counter per `ep_uuid` so a brief network flap does not abort the build.
- Preserve the existing timeout path and task-status handling.

**Step 4: Run focused tests**

Run:
- `PYTHONPATH=. pytest backend/tests/integration/test_zep_runtime_contracts.py -q`
- `PYTHONPATH=. pytest backend/tests/integration/test_local_primary_mirofish_services.py -q`

Expected: PASS. Polling should fail fast on permanent errors and still work on local-primary happy paths.

**Step 5: Optional checkpoint commit**

```bash
git add backend/app/services/graph_builder.py backend/tests/integration/test_zep_runtime_contracts.py
git commit -m "fix: fail fast on permanent zep polling errors"
```

### Task 3: Retry transient completion-poll failures in graph memory updater

**Files:**
- Modify: `backend/app/services/zep_graph_memory_updater.py`
- Modify: `backend/tests/integration/test_zep_reverse_engineering_guards.py`

**Step 1: Write the failing test**

Add a test proving that a transient `episode.get()` error does not mark the batch failed if the next poll succeeds.

```python
def test_graph_memory_updater_retries_transient_poll_failures(monkeypatch):
    import backend.app.services.zep_graph_memory_updater as updater_module

    class TransientPollError(Exception):
        pass

    class FakeEpisodeApi:
        def __init__(self):
            self.calls = 0

        def get(self, uuid_):
            self.calls += 1
            if self.calls == 1:
                raise TransientPollError("temporary network issue")
            return SimpleNamespace(processed=True, task_id=None, uuid_=uuid_)

    fake_episode_api = FakeEpisodeApi()

    class FakeGraph:
        def __init__(self):
            self.episode = fake_episode_api

        def add(self, *, graph_id, type, data):
            return SimpleNamespace(uuid_="episode-1", processed=False, task_id=None)

    class FakeZep:
        def __init__(self, api_key):
            self.graph = FakeGraph()

    monkeypatch.setattr(updater_module, "Zep", FakeZep)

    updater = ZepGraphMemoryUpdater(graph_id="graph-1", api_key="dummy")
    updater.EPISODE_POLL_INTERVAL = 0.0
    updater.EPISODE_WAIT_TIMEOUT = 0.2

    updater._send_batch_activities([activity_fixture()], "twitter")

    assert updater.get_stats()["failed_count"] == 0
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest backend/tests/integration/test_zep_reverse_engineering_guards.py -q`

Expected: FAIL because `_wait_for_episode_processing()` currently treats any polling exception as a hard failure.

**Step 3: Write minimal implementation**

In `backend/app/services/zep_graph_memory_updater.py`:
- Add a transient polling retry wrapper inside `_wait_for_episode_processing()`.
- Retry only transient errors (`ConnectionError`, `TimeoutError`, transport/5xx-like failures).
- Do not retry permanent task failures or explicit `failed/canceled` statuses.
- Keep the “do not re-send after add succeeds” rule.

**Step 4: Run focused tests**

Run:
- `PYTHONPATH=. pytest backend/tests/integration/test_zep_reverse_engineering_guards.py -q`
- `PYTHONPATH=. pytest backend/tests/integration/test_parity_simulation_run.py -q`

Expected: PASS. Polling becomes resilient without changing batch semantics.

**Step 5: Optional checkpoint commit**

```bash
git add backend/app/services/zep_graph_memory_updater.py backend/tests/integration/test_zep_reverse_engineering_guards.py
git commit -m "fix: retry transient zep memory poll failures"
```

### Task 4: Replace vague profile enrichment query with multi-query recall

**Files:**
- Modify: `backend/app/services/oasis_profile_generator.py`
- Create or Modify: `backend/tests/integration/test_zep_profile_query_guards.py`

**Step 1: Write the failing test**

Add a test proving profile enrichment issues multiple focused Zep queries instead of a single vague string.

```python
def test_profile_enrichment_uses_multiple_queries(monkeypatch):
    import backend.app.services.oasis_profile_generator as profile_module

    queries = []

    class FakeGraph:
        def search(self, **kwargs):
            queries.append(kwargs["query"])
            return SimpleNamespace(edges=[], nodes=[])

    generator = profile_module.OasisProfileGenerator(zep_api_key="dummy", graph_id="graph-1")
    generator.zep_client = SimpleNamespace(graph=FakeGraph())

    entity = SimpleNamespace(
        name="Alice Kim",
        uuid="node-1",
        summary="Launch lead at Example Labs",
        attributes={"alias": "AK"},
    )

    generator._search_zep_for_entity(entity)

    assert len(queries) >= 2
    assert any("Alice Kim" in query for query in queries)
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest backend/tests/integration/test_zep_profile_query_guards.py -q`

Expected: FAIL because `_search_zep_for_entity()` currently uses one hard-coded `comprehensive_query`.

**Step 3: Write minimal implementation**

In `backend/app/services/oasis_profile_generator.py`:
- Add a helper like `_build_entity_search_queries(entity) -> list[str]`.
- Compose 2-4 focused queries only:
  - exact entity name
  - alias if present
  - short summary-keyword query
  - optional relation-oriented query
- Reuse existing edge/node search flow, but iterate over the small query set and merge deduplicated facts/summaries.
- Keep YAGNI: do not introduce embeddings or ranking layers here.

**Step 4: Run focused tests**

Run:
- `PYTHONPATH=. pytest backend/tests/integration/test_zep_profile_query_guards.py -q`
- `PYTHONPATH=. pytest backend/tests/integration/test_zep_reverse_engineering_guards.py -q`

Expected: PASS. Query generation becomes deterministic and recall-oriented.

**Step 5: Optional checkpoint commit**

```bash
git add backend/app/services/oasis_profile_generator.py backend/tests/integration/test_zep_profile_query_guards.py
git commit -m "feat: improve zep profile enrichment query recall"
```

### Task 5: Final regression sweep

**Files:**
- Re-run only, no production changes

**Step 1: Run the targeted suite**

Run:

```bash
PYTHONPATH=. pytest \
  backend/tests/integration/test_zep_search_contract_guards.py \
  backend/tests/integration/test_zep_runtime_contracts.py \
  backend/tests/integration/test_zep_reverse_engineering_guards.py \
  backend/tests/integration/test_zep_profile_query_guards.py \
  backend/tests/integration/test_zep_contract_compatibility.py \
  backend/tests/integration/test_zep_paging_contract.py \
  backend/tests/integration/test_local_primary_mirofish_services.py \
  backend/tests/integration/test_graph_backend_modes.py \
  backend/tests/integration/test_parity_simulation_prepare.py \
  backend/tests/integration/test_parity_simulation_run.py -q
```

Expected: all green, with only known third-party warnings if any.

**Step 2: Run one smoke path manually**

Use one real or shimmed graph to verify:
- graph build
- entity read
- profile generation
- simulation start with graph memory update
- immediate read-after-write search

Document any mismatch before widening scope.

**Step 3: Summarize residual risk**

Capture:
- which failures now surface loudly instead of falling back
- which code paths still intentionally degrade
- any remaining Zep SDK ambiguities

**Step 4: Optional final commit**

```bash
git add backend/app/services backend/tests/integration docs/plans
git commit -m "fix: harden zep runtime boundary and profile recall"
```

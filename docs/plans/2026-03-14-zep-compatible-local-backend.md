# Graphiti-Backed Zep Parity Engine Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Graphiti를 엔진 코어로 활용해 MiroFish가 사용하는 Zep 기능을 결과 수준까지 최대한 근접하게 재현하는 standalone parity engine을 만들고, MiroFish의 API/UI/flow/output-file은 그대로 유지하면서 graph/search/profile/report 품질이 충분히 Zep에 근접한 경우에만 기존 코드가 `zep_cloud` 호환 adapter를 통해 이 엔진을 사용하게 만든다.

**Architecture:** 이 문서는 기존 shim-first/custom-engine-first 계획을 대체한다. 구현 순서는 `parity spec -> baseline capture -> Graphiti-backed engine service -> evaluation harness -> zep_cloud compatibility adapter -> migration/coexistence -> local cutover` 이다. 엔진은 root `app.py`로 실행되는 별도 Python 서비스이며, 기본 포트는 `8123`이다. Graphiti는 엔진의 temporal graph/retrieval core로 사용하고, MiroFish 전용 요구사항인 parity scorecard, report/profile/simulation downstream verification, `zep_cloud` contract adapter, 기존 graph migration/coexistence는 별도 레이어로 구축한다.

**Tech Stack:** Python 3.11, pip + root `requirements.txt`, Flask, pytest, Graphiti core, Kuzu backend, SQLite for parity artifacts and metadata, OpenAI-compatible LLM API, dataclasses, pydantic.

---

> **Supersedes Previous Plan**
> 이 문서는 이전의 `contract-compatible local shim` 및 `custom parity engine` 계획을 대체한다. 앞으로 이 파일 하나만 canonical plan으로 취급한다.

## Requirements Summary

- 목표는 `API/UI/flow/output-file/json shape 호환`을 유지하면서 Zep 결과에 충분히 가까운 `behavior parity`를 달성하는 것이다.
- 엔진은 `pip install -r requirements.txt` 후 `python app.py`로 실행 가능해야 한다.
- 엔진 기본 포트는 `8123`이고, 기존 MiroFish 백엔드 기본 포트와 분리되어야 한다.
- 엔진 구현을 위해 Docker, uv, 별도 시스템 서비스, 외부 DB 데몬을 필수 전제로 두지 않는다.
- Graphiti core는 leverage 대상이지만, 최종 시스템은 Graphiti 단독이 아니라 `Graphiti + parity harness + adapter + rollout control` 조합이다.
- Kuzu를 고정 backend로 사용해 pip-only 설치/실행 제약을 충족한다.
- 기본 지원 언어는 한국어와 영어다.
- 엔진은 상세 로그를 bash/terminal stdout으로 지속 출력해야 하며, 디버깅 시 파일 로그 없이도 상태를 추적할 수 있어야 한다.
- local engine은 다음 실제 사용면을 커버해야 한다.
- graph build: [backend/app/services/graph_builder.py](/Users/byeongkijeong/Codes/MiroFish-Ko/backend/app/services/graph_builder.py)
- entity read: [backend/app/services/zep_entity_reader.py](/Users/byeongkijeong/Codes/MiroFish-Ko/backend/app/services/zep_entity_reader.py)
- search/tools: [backend/app/services/zep_tools.py](/Users/byeongkijeong/Codes/MiroFish-Ko/backend/app/services/zep_tools.py)
- profile context: [backend/app/services/oasis_profile_generator.py](/Users/byeongkijeong/Codes/MiroFish-Ko/backend/app/services/oasis_profile_generator.py)
- report generation/chat/tools: [backend/app/api/report.py](/Users/byeongkijeong/Codes/MiroFish-Ko/backend/app/api/report.py), [backend/app/services/report_agent.py](/Users/byeongkijeong/Codes/MiroFish-Ko/backend/app/services/report_agent.py)
- simulation memory updates: [backend/app/services/zep_graph_memory_updater.py](/Users/byeongkijeong/Codes/MiroFish-Ko/backend/app/services/zep_graph_memory_updater.py)
- simulation prepare/env status: [backend/app/api/simulation.py](/Users/byeongkijeong/Codes/MiroFish-Ko/backend/app/api/simulation.py), [backend/app/services/simulation_manager.py](/Users/byeongkijeong/Codes/MiroFish-Ko/backend/app/services/simulation_manager.py)
- 기존 서비스 business logic는 parity threshold를 넘기기 전까지 건드리지 않는다.
- 기존 graph/project 자산도 최종적으로 import 또는 migrate 대상에 포함한다.
- `zep_cloud` 호환 adapter는 parity threshold 통과 후 마지막에 붙인다.
- 최종 adapter는 in-process 직접 엔진 구현이 아니라 standalone service에 대한 client adapter가 된다.
- `local_primary`에서는 engine 장애 시 즉시 실패하며 자동 Zep fallback은 허용하지 않는다.

## Why Graphiti

- Graphiti는 Zep 계열 temporal context graph use case와 직접적으로 맞닿아 있는 오픈소스 엔진이므로, ontology-aware extraction, episode provenance, temporal edges, hybrid retrieval을 처음부터 새로 만들 필요를 크게 줄여 준다.
- Graphiti를 사용해도 MiroFish에서 필요한 모든 parity가 자동으로 확보되지는 않는다. 특히 report/profile/simulation downstream behavior parity, `zep_cloud` field contract, rollout/shadow-eval, MiroFish-specific state/output-file/API parity는 별도 구현이 필요하다.
- Graphiti의 기본 REST service를 그대로 채택하지 않고, root `app.py`로 뜨는 MiroFish 전용 parity engine service에서 Graphiti core를 감싼다.
- Graphiti 문서 기준으로 OpenAI-compatible API 연동은 가능하다. 다만 OpenAI 호환 provider는 `OpenAIGenericClient` 경로로 명시적으로 구성해야 하며, structured output을 안정적으로 지원하지 않는 모델은 ingestion 실패 위험이 있다.
- Graphiti의 MCP/server example 구현에선 일부 경로가 환경변수 기반 `base_url` 전달을 완전히 보장하지 않을 수 있으므로, parity engine에서는 LLM client, embedder, reranker를 모두 코드에서 명시적으로 구성한다.

## Parity Definition

Zep parity는 아래 5개 축으로 정의한다.

1. **Graph Build Parity**
- 같은 문서와 같은 ontology를 넣었을 때 node/edge 구조가 충분히 비슷해야 한다.

2. **Search Parity**
- 같은 query에 대해 top-k edges/nodes/facts가 충분히 겹쳐야 한다.

3. **Profile Parity**
- same graph에서 `OasisProfileGenerator`가 만들어내는 context richness와 profile completeness가 충분히 비슷해야 한다.

4. **Report Parity**
- report tool outputs, report section generation inputs, report chat answers가 충분히 비슷해야 한다.

5. **Simulation Memory Parity**
- simulation action logs를 graph memory로 누적했을 때 search 결과 변화와 사실 축적 방식이 충분히 비슷해야 한다.

## Success Metrics

이 문서에서 “통과”는 아래 기준으로 정의한다.

- Functional parity:
  - MiroFish API/UI/flow/output-file/json shape unchanged
  - engine startup command remains `python app.py`
  - engine default port remains `8123`
  - backend/engine split remains `5001` / `8123`
- Structural parity:
  - node count delta <= 10%
  - edge count delta <= 15%
  - entity label F1 >= 0.90
  - edge type F1 >= 0.85
  - attribute fill-rate parity >= 0.85
- Retrieval parity:
  - top-10 edge overlap >= 0.80
  - top-10 node overlap >= 0.80
  - nDCG@10 >= 0.85
  - fact hit-rate >= 0.85
- Downstream parity:
  - simulation prepare success rate = 100%
  - profile completeness score >= 0.90 of Zep baseline
  - report tool usefulness score >= 4/5 on golden corpus review rubric
  - report generation/chat path exception rate = 0

If these thresholds are not met, `local_primary` cutover is blocked.

## Public Contract Inventory

Graphiti-backed engine와 final adapter는 이 Zep-facing contract를 보존해야 한다. 기존 코드가 직접 이 호출과 필드를 읽기 때문이다.

- package exports:
- `zep_cloud.EpisodeData`
- `zep_cloud.EntityEdgeSourceTarget`
- `zep_cloud.InternalServerError`
- `zep_cloud.external_clients.ontology.EntityModel`
- `zep_cloud.external_clients.ontology.EntityText`
- `zep_cloud.external_clients.ontology.EdgeModel`
- `graph.create(graph_id, name, description)`
- `graph.set_ontology(graph_ids, entities, edges)`
- `graph.add_batch(graph_id, episodes)`
- `graph.add(graph_id, type, data)`
- `graph.search(graph_id, query, limit, scope, reranker)`
- `graph.delete(graph_id=...)`
- `graph.node.get_by_graph_id(graph_id, limit, uuid_cursor=None)`
- `graph.node.get(uuid_=...)`
- `graph.node.get_entity_edges(node_uuid=...)`
- `graph.edge.get_by_graph_id(graph_id, limit, uuid_cursor=None)`
- `graph.episode.get(uuid_=...)`

The returned objects must preserve these fields:

- node: `uuid_`, `name`, `labels`, `summary`, `attributes`, `created_at`
- edge: `uuid_`, `name`, `fact`, `fact_type`, `source_node_uuid`, `target_node_uuid`, `attributes`, `created_at`, `valid_at`, `invalid_at`, `expired_at`, `episodes|episode_ids`
- episode: `uuid_`, `processed`
- search result: `.edges`, `.nodes`

## Observed Zep I/O Examples

The following examples were captured from a live temporary Zep graph probe on 2026-03-14 using the currently installed `zep-cloud` SDK. These examples are canonical design inputs for the adapter and parity harness.

### Observed Ontology Constraints

- `set_ontology` rejects entity or edge models without descriptions.
- edge names must be in `SCREAMING_SNAKE_CASE`.
- the currently installed SDK exposes `client.graph.node.get_edges(node_uuid=...)`; existing MiroFish code expects `get_entity_edges(...)`, so the compatibility adapter must provide an alias or wrapper for that mismatch.

### Example: `graph.create(...)`

```json
{
  "graph_id": "mirofish_probe_<redacted>",
  "name": "MiroFish Probe",
  "description": "temporary probe graph",
  "type": "Graph"
}
```

### Example: `graph.add_batch(...)`

```json
{
  "count": 1,
  "episode_uuids": ["<episode_uuid>"],
  "episode_uuid": "<episode_uuid>",
  "processed_initial": false,
  "type": "Episode"
}
```

### Example: `graph.episode.get(...)`

```json
{
  "episode_uuid": "<episode_uuid>",
  "processed": true,
  "type": "Episode"
}
```

### Example: `graph.node.get_by_graph_id(...)`

```json
[
  {
    "uuid_": "<node_uuid>",
    "name": "Alice",
    "labels": ["Person"],
    "summary": "Alice is employed by Example Labs.",
    "attributes": {
      "name": "Alice",
      "role": "Worker"
    },
    "created_at": "2026-03-14T05:39:35.252Z"
  },
  {
    "uuid_": "<node_uuid>",
    "name": "Example Labs",
    "labels": ["Company"],
    "summary": "Alice is employed by Example Labs.\nExample Labs develops robotics software.\nExample Labs develops robotics software.",
    "attributes": {
      "industry": "Robotics Software",
      "name": "Example Labs"
    },
    "created_at": "2026-03-14T05:39:35.252Z"
  }
]
```

### Example: `graph.edge.get_by_graph_id(...)`

```json
[
  {
    "uuid_": "<edge_uuid>",
    "name": "WORKS_FOR",
    "fact": "Alice is employed by Example Labs.",
    "fact_type": null,
    "source_node_uuid": "<node_uuid>",
    "target_node_uuid": "<node_uuid>",
    "attributes": {
      "edge_type": "WORKS_FOR",
      "fact": "Alice is employed by Example Labs.",
      "since": "2026-03-14 05:39:34.106735+00:00"
    },
    "created_at": "2026-03-14T05:39:37.386Z",
    "valid_at": "2026-03-14T05:39:34.106Z",
    "invalid_at": null,
    "expired_at": null,
    "episodes": ["<episode_uuid>"]
  }
]
```

### Example: `graph.node.get(...)`

```json
{
  "uuid_": "<node_uuid>",
  "name": "Alice",
  "labels": ["Person"],
  "summary": "Alice is employed by Example Labs.",
  "attributes": {
    "name": "Alice",
    "role": "Worker"
  }
}
```

### Example: `graph.node.get_edges(...)`

```json
[
  {
    "uuid_": "<edge_uuid>",
    "name": "WORKS_FOR",
    "fact": "Alice is employed by Example Labs.",
    "source_node_uuid": "<node_uuid>",
    "target_node_uuid": "<node_uuid>"
  }
]
```

### Example: `graph.search(..., scope=\"edges\")`

```json
[
  {
    "uuid_": "<edge_uuid>",
    "name": "BUILDS",
    "fact": "Example Labs develops robotics software.",
    "source_node_uuid": "<node_uuid>",
    "target_node_uuid": "<node_uuid>"
  },
  {
    "uuid_": "<edge_uuid>",
    "name": "WORKS_FOR",
    "fact": "Alice is employed by Example Labs.",
    "source_node_uuid": "<node_uuid>",
    "target_node_uuid": "<node_uuid>"
  }
]
```

### Example: `graph.search(..., scope=\"nodes\")`

```json
[
  {
    "uuid_": "<node_uuid>",
    "name": "Example Labs",
    "labels": ["Company"],
    "summary": "Alice is employed by Example Labs.\nExample Labs develops robotics software.\nExample Labs develops robotics software."
  },
  {
    "uuid_": "<node_uuid>",
    "name": "Alice",
    "labels": ["Person"],
    "summary": "Alice is employed by Example Labs."
  }
]
```

## Codebase Facts

- Graph build and polling contract lives in [backend/app/services/graph_builder.py](/Users/byeongkijeong/Codes/MiroFish-Ko/backend/app/services/graph_builder.py).
- Entity read and edge context contract lives in [backend/app/services/zep_entity_reader.py](/Users/byeongkijeong/Codes/MiroFish-Ko/backend/app/services/zep_entity_reader.py).
- Search result shape and downstream tooling contract lives in [backend/app/services/zep_tools.py](/Users/byeongkijeong/Codes/MiroFish-Ko/backend/app/services/zep_tools.py).
- Profile generation relies on separate `scope="edges"` and `scope="nodes"` searches in [backend/app/services/oasis_profile_generator.py](/Users/byeongkijeong/Codes/MiroFish-Ko/backend/app/services/oasis_profile_generator.py).
- Report generation and chat rely on graph search/statistics tool outputs in [backend/app/api/report.py](/Users/byeongkijeong/Codes/MiroFish-Ko/backend/app/api/report.py) and [backend/app/services/report_agent.py](/Users/byeongkijeong/Codes/MiroFish-Ko/backend/app/services/report_agent.py).
- Simulation prepare and env-status flows rely on graph-backed profile/config generation in [backend/app/api/simulation.py](/Users/byeongkijeong/Codes/MiroFish-Ko/backend/app/api/simulation.py) and [backend/app/services/simulation_manager.py](/Users/byeongkijeong/Codes/MiroFish-Ko/backend/app/services/simulation_manager.py).
- Graph memory update relies on batched `graph.add(...)` in [backend/app/services/zep_graph_memory_updater.py](/Users/byeongkijeong/Codes/MiroFish-Ko/backend/app/services/zep_graph_memory_updater.py).

## Runtime Constraints

- canonical engine entrypoint: `python app.py`
- default engine port: `8123`
- install path: `pip install -r requirements.txt`
- root `requirements.txt` is the canonical install entrypoint for the parity engine work and must either supersede or include the backend requirements transitively
- MiroFish backend remains a separate process and talks to the engine through `ENGINE_BASE_URL`
- existing MiroFish backend default port remains `5001`
- existing frontend target and UI flow remain unchanged; engine `8123` is an internal dependency port, not a frontend-facing replacement port
- Graphiti backend choice must remain pip-installable and embedded; Kuzu is the default
- any plan item that requires a non-pip-managed runtime dependency is out of scope unless replaced by a Python package
- default human-facing language support must include Korean and English
- engine logs must be visible in bash stdout/stderr by default

## Runtime Configuration

This section is the canonical runtime configuration contract for the project after implementation.

### Backend Selection

- `GRAPH_BACKEND=zep`
  - 기존 Zep API를 source of truth로 사용한다.
- `GRAPH_BACKEND=shadow_eval`
  - 선택적 진단 모드다. 기존 Zep API는 그대로 source of truth로 사용하고, Graphiti-backed engine을 병렬로 실행해 parity artifact와 scorecard만 수집한다.
- `GRAPH_BACKEND=local_primary`
  - Graphiti-backed parity engine을 source of truth로 사용한다. `zep_cloud` adapter는 이 모드에서 엔진 service에 연결된다.

### Engine Connection

- `ENGINE_BASE_URL`
  - default: `http://127.0.0.1:8123`
- `ENGINE_HOST`
  - default: `127.0.0.1`
- `ENGINE_PORT`
  - default: `8123`
- `ENGINE_TIMEOUT_SECONDS`
  - default: `30`
- `ENGINE_SHADOW_EVAL_ENABLED`
  - default: `false`

### Graphiti Core

- `GRAPHITI_BACKEND`
  - fixed: `kuzu`
- `GRAPHITI_DB_PATH`
  - example: `./data/graphiti.kuzu`
- `GRAPHITI_DEFAULT_GROUP_ID`
  - optional, default group/partition id
- `GRAPHITI_INGEST_CONCURRENCY`
  - optional, ingestion worker count
- `GRAPHITI_EPISODE_INLINE`
  - default: `false`
  - test mode에서는 `true`로 override 가능
- `GRAPHITI_SEARCH_TOP_K`
  - optional
- `GRAPHITI_EDGE_TOP_K`
  - optional
- `GRAPHITI_NODE_TOP_K`
  - optional
- `GRAPHITI_RERANK_ENABLED`
  - default: `true`
- `GRAPHITI_PARITY_ARTIFACT_DIR`
  - example: `./artifacts/parity`
- `GRAPHITI_LOG_LEVEL`
  - default: `INFO`
- `GRAPHITI_DEFAULT_LANGUAGES`
  - default: `ko,en`
- `GRAPHITI_STDOUT_LOGGING`
  - default: `true`

### Graphiti LLM and Embeddings

- `GRAPHITI_LLM_BASE_URL`
- `GRAPHITI_LLM_API_KEY`
- `GRAPHITI_LLM_MODEL`
- `GRAPHITI_EMBEDDING_BASE_URL`
- `GRAPHITI_EMBEDDING_API_KEY`
- `GRAPHITI_EMBEDDING_MODEL`
- `GRAPHITI_RERANK_BASE_URL`
- `GRAPHITI_RERANK_API_KEY`
- `GRAPHITI_RERANK_MODEL`

LLM and embedding configuration must be namespaced separately from existing MiroFish LLM config to avoid hidden coupling.
OpenAI-compatible providers must be wired explicitly in code, not inferred only from ambient `OPENAI_BASE_URL`.

### OpenAI-Compatible Provider Policy

- The engine must support these providers in the first implementation:
  - OpenAI-compatible OpenAI
  - OpenRouter
  - Ollama
  - LM Studio
- The four providers above are all first-class targets in v1.
- None of them may be downgraded to `dev-only`, `search-only`, or `partial-support` in the first release.
- Minimum capability requirements are identical across all four:
  - structured output for ingestion workloads
  - embedding generation
  - rerank or equivalent scoring path
  - timeout/retry handling
- If the provider is any OpenAI-compatible endpoint, the engine must:
  - instantiate `AsyncOpenAI(base_url=..., api_key=...)`
  - use Graphiti's generic OpenAI-compatible LLM client path
  - configure the embedder with the same explicit `base_url`
  - configure the reranker/cross-encoder with the same explicit `base_url`
- Do not rely on Graphiti MCP server defaults or environment-variable-only propagation for reranker configuration.
- During parity evaluation, any provider that fails structured output conformance is rejected for ingestion workloads even if basic chat completion works.

### Minimal Dev Preset

```env
GRAPH_BACKEND=zep

ENGINE_BASE_URL=http://127.0.0.1:8123
ENGINE_HOST=127.0.0.1
ENGINE_PORT=8123
ENGINE_TIMEOUT_SECONDS=30
ENGINE_SHADOW_EVAL_ENABLED=true

GRAPHITI_BACKEND=kuzu
GRAPHITI_DB_PATH=./data/graphiti.kuzu
GRAPHITI_RERANK_ENABLED=true
GRAPHITI_DEFAULT_LANGUAGES=ko,en
GRAPHITI_STDOUT_LOGGING=true

GRAPHITI_LLM_BASE_URL=https://api.openai.com/v1
GRAPHITI_LLM_API_KEY=YOUR_KEY
GRAPHITI_LLM_MODEL=gpt-4.1-mini

GRAPHITI_EMBEDDING_BASE_URL=https://api.openai.com/v1
GRAPHITI_EMBEDDING_API_KEY=YOUR_KEY
GRAPHITI_EMBEDDING_MODEL=text-embedding-3-large
```

### Dev Orchestration Update (2026-03-15)

- root `npm run dev`는 local-primary oriented local development에서 parity engine, backend, frontend를 함께 올릴 수 있어야 한다.
- local dev orchestration은 cutover gate 우회를 위해 `GRAPHITI_ALLOW_LOCAL_EVAL=true`를 세션 한정으로 주입할 수 있다. 이 우회는 개발 편의 전용이며 production/runtime default를 바꾸지 않는다.
- backend startup path는 `GRAPH_BACKEND=local_primary`일 때 `ENGINE_BASE_URL`의 `/health` 및 `/ready`를 확인하고, engine이 준비되지 않았으면 fail-fast 해야 한다.
- engine이 내려가 있거나 연결이 거부되면 raw adapter traceback 대신 explicit operational error를 surface 해야 한다.
- root dev orchestration은 backend `uv` environment와 별도로 parity engine용 root virtualenv 또는 동등한 isolated Python environment를 관리할 수 있다. backend dependency graph와 engine dependency graph를 강제로 단일 lockfile로 합치지 않는다.

### Minimal Test Preset

```env
GRAPH_BACKEND=local_primary
ENGINE_BASE_URL=http://127.0.0.1:8123
ENGINE_HOST=127.0.0.1
ENGINE_PORT=8123
GRAPHITI_BACKEND=kuzu
GRAPHITI_DB_PATH=./tmp/test-graphiti.kuzu
GRAPHITI_EPISODE_INLINE=true
ENGINE_TIMEOUT_SECONDS=5
GRAPHITI_DEFAULT_LANGUAGES=ko,en
GRAPHITI_STDOUT_LOGGING=true
```

## Hard Compatibility Gates

These are stricter than the parity score thresholds above. They must all pass before the project can claim "MiroFish-compatible engine" status.

- all existing MiroFish backend routes that currently depend on Zep complete without unhandled exceptions in `local_primary`
- backend response schemas remain unchanged for graph, simulation, report, and tool endpoints
- the following route groups are explicitly included in the gate:
  - graph build/data/delete/task flows
  - simulation entities/prepare/generate_profiles/start/env_status flows
  - report generate/chat/search/statistics flows
- state transitions remain unchanged for project build tasks, simulation prepare, simulation run, and report generation
- simulation start, run status, stop, and graph memory update flows remain unchanged end-to-end
- output files remain unchanged in name and basic format:
  - `reddit_profiles.json`
  - `twitter_profiles.csv`
  - simulation config artifacts
  - persisted report artifacts
- frontend setup/status flow still treats the environment as healthy without requiring frontend code changes
- existing backend process still runs on `5001`; parity engine runs on `8123`; no route collision or proxy confusion
- `python app.py` is sufficient to boot the parity engine once dependencies are installed with pip
- engine service exposes stable `/health` and `/ready` endpoints and backend/runtime checks consume them
- existing graph/project identifiers remain valid across `zep` and `local_primary`, or an explicit migration/import procedure exists and passes verification
- migration/import preserves original `graph_id`
- migration/import is atomic at the chosen migration unit; failures rollback and keep the existing Zep state as source of truth
- Korean and English inputs both complete the same graph/profile/report/simulation flows without language-specific breakage
- engine emits detailed operational logs to bash stdout/stderr by default for boot, ingest, search, parity evaluation, migration, and adapter requests

## Non-Goals

- Bit-for-bit identical internal implementation to Zep Cloud
- Reverse engineering hidden Zep models or proprietary ranking internals
- Directly using Graphiti's stock server without MiroFish-specific parity and adapter layers
- Single-iteration cutover without shadow evaluation

## Risks and Mitigations

- Graphiti capabilities diverge from the exact Zep behavior MiroFish implicitly depends on
  - Mitigation: baseline corpus and explicit score thresholds come before adapter cutover.
- OpenAI-compatible provider wiring may partially work for chat but fail for rerank or ingestion schema output
  - Mitigation: explicitly instantiate LLM/embedder/reranker clients with `base_url` and add a dedicated compatibility smoke test before parity runs.
- Adapter-first work hides engine quality problems
  - Mitigation: adapter is delayed until the final task.
- Search parity is weaker than graph parity
  - Mitigation: use Graphiti retrieval first, add rerank overlays and explicit top-k overlap metrics.
- Downstream parity fails even if graph counts look good
  - Mitigation: profile/report/simulation parity tests are separate gates.
- Graphiti backend or API surface changes over time
  - Mitigation: isolate Graphiti behind MiroFish-owned service and internal abstractions.
- Long project with uncertain stopping point
  - Mitigation: explicit score thresholds and route-level hard gates.
- Separate engine process introduces new failure modes
  - Mitigation: readiness/health contract, startup ordering checks, and explicit backend diagnostics when `ENGINE_BASE_URL` is unreachable.
- Existing Zep-backed graph/project assets may not map cleanly to local-primary rollout
  - Mitigation: define import/migration path as a required delivery item before claiming full compatibility.

## Failure Semantics

- In `local_primary`, engine unavailability is a hard failure.
- Backend must not silently retry against Zep in `local_primary`.
- If `ENGINE_BASE_URL` is unreachable:
  - backend returns an explicit operational error
  - logs identify engine connectivity failure
  - no partial success response is returned
- local dev/task orchestration also follows the same rule:
  - if engine startup/readiness check fails, backend must not keep serving local-primary graph builds as if the graph backend were healthy
  - graph build task failure must surface `Parity engine is unavailable`-class operational messaging instead of a raw connect traceback
- `graph.add_batch(...)` in the parity engine must be queue-and-return, not process-and-block:
  - batch request creates `episode_uuid` records and returns immediately
  - backend polls `graph.episode.get(...)` for completion
  - provider-backed ingestion latency must not hold the HTTP batch request open until completion
- If engine returns malformed payload:
  - backend treats it as adapter/engine failure
  - response is a server error with diagnostic logging
- If `/ready` is unhealthy:
  - startup checks fail
  - routes depending on the engine fail fast
- All critical failures must be visible in bash stdout/stderr with structured context:
  - route or job name
  - graph_id / project_id / simulation_id when available
  - provider/backend mode
  - exception type
  - retry/fail-fast decision

## Migration and Coexistence Contract

- Existing Zep graphs and projects are migration targets.
- Migration unit is **project-level**.
- Migrated graphs must preserve original `graph_id`.
- Migration is atomic per selected migration unit.
- If migration fails:
  - rollback the local import
  - keep existing Zep state unchanged
  - do not switch the affected project to `local_primary`
- Migration verification must compare:
  - graph structure
  - search behavior
  - profile/report downstream outputs
  - state/output-file compatibility

## Provider Capability Matrix

The four supported providers are all first-class targets in v1. If a provider cannot satisfy the required capabilities below, it is treated as **unsupported**, not partially supported.

| Provider | Structured Output | Embeddings | Rerank / Equivalent | Timeout / Retry | V1 Status |
|----------|-------------------|------------|----------------------|-----------------|-----------|
| OpenAI | Required | Required | Required | Required | Must support |
| OpenRouter | Required | Required | Required | Required | Must support |
| Ollama | Required | Required | Required | Required | Must support |
| LM Studio | Required | Required | Required | Required | Must support |

No provider may be marked `dev-only`, `search-only`, `partial-support`, or `best-effort` in the first release.

## Corpus Case Catalog

Initial parity corpus contains 3 to 5 named cases. These names are canonical and should be used in fixtures, baseline artifacts, scorecards, and reports.

1. `ko_alias_case`
- language: Korean
- purpose: alias-heavy entity normalization
- focus: person/organization alias merge, node/edge identity stability

2. `en_temporal_case`
- language: English
- purpose: temporal relationship and fact lifecycle
- focus: `valid_at`, `invalid_at`, `expired_at`, edge replacement behavior

3. `ko_report_case`
- language: Korean
- purpose: report generation and tool usefulness
- focus: graph search -> report tools -> report generation/chat

4. `en_profile_case`
- language: English
- purpose: profile context and completeness
- focus: `OasisProfileGenerator`, node/edge search quality, summary usefulness

5. `sim_memory_case`
- language: mixed or minimal bilingual
- purpose: simulation memory ingestion
- focus: `graph.add(...)` effects, simulation prepare/run/memory update retrievability

The corpus is intentionally small but mandatory. A future expansion may add more cases, but these names and purposes are fixed for v1.

## Endpoint Inventory

The following endpoint groups are parity-critical and must be covered explicitly in tests and hard gates.

| Endpoint Group | Examples | Parity Required | Hard Gate | Primary Test Target |
|----------------|----------|-----------------|-----------|---------------------|
| Graph APIs | build, data, delete, task | Yes | Yes | graph builder + adapter integration tests |
| Simulation Entity APIs | entities, entity detail, by-type | Yes | Yes | simulation entity integration tests |
| Simulation Prepare/Profile APIs | prepare, generate_profiles, get_profiles, get_config | Yes | Yes | simulation prepare/profile tests |
| Simulation Run APIs | start, stop, run status, detail | Yes | Yes | simulation run tests |
| Report Tool APIs | search, statistics | Yes | Yes | report tool tests |
| Report Generation APIs | generate, status, sections, progress | Yes | Yes | report generation tests |
| Report Chat APIs | chat_with_report_agent | Yes | Yes | report chat tests |
| Env Status APIs | get_env_status, close_env related flows | Yes | Yes | env status tests |

If an endpoint is not covered by the categories above, it must be explicitly classified as either:
- included in parity scope
- out of parity scope for v1

## Error Response Examples

The backend-to-frontend error behavior must be stable and explicit.

### Engine Unavailable

```json
{
  "success": false,
  "error": "Parity engine is unavailable",
  "engine_status": "unavailable"
}
```

Recommended status code: `503`

### Engine Malformed Response

```json
{
  "success": false,
  "error": "Parity engine returned an invalid response",
  "engine_status": "invalid_response"
}
```

Recommended status code: `500`

### Migration Failed

```json
{
  "success": false,
  "error": "Graph migration failed and was rolled back",
  "migration_status": "rolled_back"
}
```

Recommended status code: `500`

## Log Field Contract

Detailed bash stdout/stderr logs must include these fields wherever applicable:

- `timestamp`
- `level`
- `mode` (`zep`, `shadow_eval`, `local_primary`)
- `route`
- `graph_id`
- `project_id`
- `simulation_id`
- `provider`
- `latency_ms`
- `result_count`
- `error_type`
- `decision` (`retry`, `fail_fast`, `rollback`, `continue`)

## Corpus Governance

- Initial parity corpus size is intentionally small: 3 to 5 cases.
- These cases must still cover distinct risk classes:
  - alias-heavy entity case
  - temporal/relationship-heavy case
  - report/profile-heavy case
  - simulation-memory-heavy case
  - optional multi-document case
- The corpus is a minimum gate, not proof of universal parity.
- Each corpus item must be versioned and reproducible.
- Raw Zep artifacts used for comparison must be stored with redaction where necessary.
- Corpus must include Korean and English cases in the initial 3 to 5 cases.

## Verification Strategy

There are four verification layers.

1. **Unit**
- storage, episode lifecycle, resolver overlays, temporal facts, search ranking, summary generation.

2. **Graphiti Integration**
- verify Graphiti+Kuzu service boot, health/readiness, ingestion, retrieval, persistence, and background processing.

3. **Parity Harness**
- run the same corpus through Zep and Graphiti-backed engine
- compare structural, retrieval, downstream metrics
- produce corpus scorecards and fail below thresholds

4. **MiroFish Integration**
- run the existing API and service flows unchanged
- verify state transitions, output files, JSON shapes, report/profile/simulation end-to-end
- verify engine unavailable behavior and startup ordering
- verify coexistence or migration behavior for existing graph/project identifiers

## Task Breakdown

### Task 1: Parity Corpus and Artifact Schema

**Files:**
- Create: `requirements.txt`
- Create: `backend/tests/parity_engine/fixtures/corpus_manifest.json`
- Create: `backend/tests/parity_engine/fixtures/README.md`
- Create: `backend/app/parity_engine/contracts.py`
- Create: `backend/tests/parity_engine/test_contracts.py`

**Step 1: Write the failing test**

```python
from backend.app.parity_engine.contracts import CorpusItem, BaselineSnapshot


def test_corpus_contract_has_required_sections():
    item = CorpusItem.model_validate({
        "id": "campus_case_01",
        "documents": ["docs/a.md"],
        "simulation_requirement": "Analyze campus activism dynamics",
        "queries": ["student protest", "faculty reaction"],
        "expected_outputs": ["graph", "search", "profile", "report", "memory_update"],
    })
    assert item.id == "campus_case_01"
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/parity_engine/test_contracts.py -q`

Expected: FAIL because `app.parity_engine.contracts` does not exist

**Step 3: Write minimal implementation**

Create typed schemas for:

- `CorpusItem`
- `BaselineSnapshot`
- `GraphSnapshot`
- `SearchSnapshot`
- `ProfileSnapshot`
- `ReportSnapshot`
- `MemoryUpdateSnapshot`
- `ParityScorecard`

Also create root `requirements.txt` that installs:

- MiroFish backend dependencies needed for parity work
- Graphiti core
- Graphiti Kuzu support
- pytest and parity test dependencies

The root `requirements.txt` must be the single documented install entrypoint and must not require the operator to separately install `backend/requirements.txt`.

Each corpus item must declare:

- input documents
- ontology input or generation mode
- search queries
- expected downstream flows to run

**Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/parity_engine/test_contracts.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add requirements.txt backend/app/parity_engine/contracts.py backend/tests/parity_engine/fixtures backend/tests/parity_engine/test_contracts.py
git commit -m "feat: add parity corpus contracts"
```

### Task 2: Zep Baseline Capture Harness

**Files:**
- Create: `backend/app/parity_engine/baseline_capture.py`
- Create: `backend/tests/parity_engine/test_baseline_capture.py`
- Create: `backend/tests/parity_engine/golden/.gitkeep`

**Step 1: Write the failing test**

```python
from backend.app.parity_engine.baseline_capture import build_artifact_paths


def test_build_artifact_paths_returns_stable_layout(tmp_path):
    paths = build_artifact_paths(tmp_path, "campus_case_01")
    assert paths["graph"].name == "graph.json"
    assert paths["search"].name == "search.json"
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/parity_engine/test_baseline_capture.py -q`

Expected: FAIL because baseline capture module does not exist

**Step 3: Write minimal implementation**

Implement a runner that:

- loads one corpus item
- runs MiroFish against real Zep
- records the raw request/response examples for the core Zep operations listed in `Observed Zep I/O Examples`
- captures artifacts for:
  - graph nodes/edges
  - search top-k results
  - profile generation context
  - report tool outputs
  - memory update delta results
- saves them under:

```text
backend/tests/parity_engine/golden/<case_id>/
  graph.json
  search.json
  profile.json
  report.json
  memory_update.json
  metadata.json
  raw_api_examples.json
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/parity_engine/test_baseline_capture.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/parity_engine/baseline_capture.py backend/tests/parity_engine/test_baseline_capture.py backend/tests/parity_engine/golden/.gitkeep
git commit -m "feat: add zep baseline capture harness"
```

### Task 3: Parity Metrics and Scorecard

**Files:**
- Create: `backend/app/parity_engine/metrics.py`
- Create: `backend/app/parity_engine/scorecard.py`
- Create: `backend/tests/parity_engine/test_metrics.py`

**Step 1: Write the failing test**

```python
from backend.app.parity_engine.metrics import overlap_at_k, relative_delta


def test_overlap_at_k():
    assert overlap_at_k(["a", "b", "c"], ["b", "c", "d"], 3) == 2 / 3


def test_relative_delta():
    assert relative_delta(100, 110) == 0.10
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/parity_engine/test_metrics.py -q`

Expected: FAIL because metrics module does not exist

**Step 3: Write minimal implementation**

Implement metric helpers and a scorecard evaluator for:

- node count delta
- edge count delta
- label F1
- edge type F1
- attribute fill-rate parity
- top-k overlap
- nDCG@k
- fact hit-rate
- downstream completeness scores

Add a cutover verdict:

- `fail`
- `shadow_only`
- `eligible_for_local_primary`

**Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/parity_engine/test_metrics.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/parity_engine/metrics.py backend/app/parity_engine/scorecard.py backend/tests/parity_engine/test_metrics.py
git commit -m "feat: add parity scorecard metrics"
```

### Task 4: Graphiti-Backed Engine Service Skeleton

**Files:**
- Create: `app.py`
- Create: `backend/app/parity_engine/server.py`
- Create: `backend/app/parity_engine/config.py`
- Create: `backend/app/parity_engine/provider_factory.py`
- Create: `backend/app/parity_engine/logging_config.py`
- Create: `backend/tests/integration/test_engine_service_boot.py`
- Create: `backend/tests/integration/test_openai_compatible_config.py`
- Create: `backend/tests/integration/test_engine_health_ready.py`
- Create: `backend/tests/integration/test_stdout_logging.py`

**Step 1: Write the failing test**

```python
from backend.app.parity_engine.server import create_engine_app


def test_engine_service_defaults_to_port_8123():
    app, config = create_engine_app(testing=True)
    assert config["PORT"] == 8123
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/integration/test_engine_service_boot.py -q`

Expected: FAIL because engine service entrypoint does not exist

**Step 3: Write minimal implementation**

Create:

- root `app.py`
- `create_engine_app(testing=False)` factory
- health endpoint
- readiness endpoint
- config object with default port `8123`
- logging config that writes detailed operational logs to stdout/stderr by default
- startup config that reads `ENGINE_BASE_URL`, `PORT`, `GRAPHITI_BACKEND=kuzu`
- provider factory that can build:
  - standard OpenAI clients
  - Azure OpenAI compatibility clients
  - generic OpenAI-compatible clients for Ollama/LM Studio/custom endpoints

Local run command must be:

```bash
pip install -r requirements.txt
python app.py
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/integration/test_engine_service_boot.py backend/tests/integration/test_engine_health_ready.py backend/tests/integration/test_openai_compatible_config.py backend/tests/integration/test_stdout_logging.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add app.py backend/app/parity_engine/server.py backend/app/parity_engine/config.py backend/app/parity_engine/provider_factory.py backend/app/parity_engine/logging_config.py backend/tests/integration/test_engine_service_boot.py backend/tests/integration/test_engine_health_ready.py backend/tests/integration/test_openai_compatible_config.py backend/tests/integration/test_stdout_logging.py
git commit -m "feat: add graphiti-backed parity engine service skeleton"
```

### Task 5: Graphiti Core Integration and Persistence

**Files:**
- Create: `backend/app/parity_engine/graphiti_client.py`
- Create: `backend/app/parity_engine/storage.py`
- Create: `backend/app/parity_engine/episodes.py`
- Create: `backend/app/parity_engine/models.py`
- Create: `backend/tests/parity_engine/test_storage.py`
- Create: `backend/tests/parity_engine/test_graphiti_integration.py`

**Step 1: Write the failing test**

```python
from backend.app.parity_engine.graphiti_client import GraphitiEngine


def test_graphiti_engine_creates_graph_and_episode(tmp_path):
    engine = GraphitiEngine(db_path=tmp_path / "graphiti.kuzu")
    graph_id = engine.create_graph("Parity Test", "desc")
    episode_id = engine.create_episode(graph_id, "Alice founded Example Labs.")
    assert graph_id.startswith("mirofish_")
    assert episode_id
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/parity_engine/test_storage.py backend/tests/parity_engine/test_graphiti_integration.py -q`

Expected: FAIL because Graphiti wrapper does not exist

**Step 3: Write minimal implementation**

Implement:

- Graphiti initialization with Kuzu
- explicit provider wiring for llm, embedder, and reranker using the factory from Task 4
- graph create/delete
- episode ingest
- ontology persistence
- local metadata persistence for parity runs

Episode state machine must include:

- `queued`
- `processing`
- `processed`
- `failed`

**Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/parity_engine/test_storage.py backend/tests/parity_engine/test_graphiti_integration.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/parity_engine/graphiti_client.py backend/app/parity_engine/storage.py backend/app/parity_engine/episodes.py backend/app/parity_engine/models.py backend/tests/parity_engine/test_storage.py backend/tests/parity_engine/test_graphiti_integration.py
git commit -m "feat: add graphiti core integration and persistence"
```

### Task 6: Ontology Mapping and Extraction Pipeline Overlay

**Files:**
- Create: `backend/app/parity_engine/ontology.py`
- Create: `backend/app/parity_engine/extractor.py`
- Create: `backend/tests/parity_engine/test_extractor.py`
- Create: `backend/tests/parity_engine/test_multilingual_extractor.py`

**Step 1: Write the failing test**

```python
from backend.app.parity_engine.extractor import GraphitiExtractionOverlay


def test_graphiti_overlay_returns_entities_and_edges():
    overlay = GraphitiExtractionOverlay()
    ontology = {
        "entity_types": [{"name": "Person", "attributes": []}],
        "edge_types": [{"name": "works_for", "source_targets": [{"source": "Person", "target": "Company"}], "attributes": []}],
    }
    result = overlay.extract("Alice works for Example Labs.", ontology)
    assert "entities" in result
    assert "edges" in result
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/parity_engine/test_extractor.py -q`

Expected: FAIL because overlay does not exist

**Step 3: Write minimal implementation**

Implement:

- Graphiti-compatible ontology normalization
- extraction overlay for MiroFish ontology format
- deterministic stub mode for tests
- source span/provenance retention

This layer exists because MiroFish ontology generation format and Graphiti ingestion format are not identical.
The initial implementation must support Korean and English documents as first-class inputs.

**Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/parity_engine/test_extractor.py backend/tests/parity_engine/test_multilingual_extractor.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/parity_engine/ontology.py backend/app/parity_engine/extractor.py backend/tests/parity_engine/test_extractor.py backend/tests/parity_engine/test_multilingual_extractor.py
git commit -m "feat: add graphiti ontology and extraction overlay"
```

### Task 7: Entity Resolution, Temporal Fact Lifecycle, and Retrieval Overlay

**Files:**
- Create: `backend/app/parity_engine/resolver.py`
- Create: `backend/app/parity_engine/temporal.py`
- Create: `backend/app/parity_engine/search.py`
- Create: `backend/app/parity_engine/summaries.py`
- Create: `backend/tests/parity_engine/test_resolution.py`
- Create: `backend/tests/parity_engine/test_search.py`

**Step 1: Write the failing test**

```python
from backend.app.parity_engine.resolver import EntityResolver
from backend.app.parity_engine.search import HybridSearchOverlay


def test_entity_resolver_merges_aliases():
    resolver = EntityResolver()
    assert resolver.should_merge(
        {"name": "MIT", "type": "University"},
        {"name": "Massachusetts Institute of Technology", "type": "University"},
    ) is True


def test_hybrid_search_overlay_returns_ranked_edges_and_nodes():
    overlay = HybridSearchOverlay()
    result = overlay.rank(
        query="student protest",
        node_candidates=[{"uuid": "n1", "summary": "Student protest leader"}],
        edge_candidates=[{"uuid": "e1", "fact": "Students organized a protest"}],
    )
    assert "nodes" in result
    assert "edges" in result
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/parity_engine/test_resolution.py backend/tests/parity_engine/test_search.py -q`

Expected: FAIL because overlays do not exist

**Step 3: Write minimal implementation**

Implement:

- canonical entity identity rules
- alias handling
- merge confidence thresholds
- temporal edge lifecycle overlay
- Graphiti retrieval + MiroFish-specific rerank overlay
- node/relation/community-like summaries
- explicit OpenAI-compatible reranker configuration; do not rely on hidden default OpenAI endpoint resolution

This task must explicitly preserve:

- `created_at`
- `valid_at`
- `invalid_at`
- `expired_at`

**Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/parity_engine/test_resolution.py backend/tests/parity_engine/test_search.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/parity_engine/resolver.py backend/app/parity_engine/temporal.py backend/app/parity_engine/search.py backend/app/parity_engine/summaries.py backend/tests/parity_engine/test_resolution.py backend/tests/parity_engine/test_search.py
git commit -m "feat: add graphiti parity overlays for resolution temporal and search"
```

### Task 8: Downstream Parity Harness for Profile, Report, and Simulation

**Files:**
- Create: `backend/app/parity_engine/evaluator.py`
- Create: `backend/tests/parity_engine/test_downstream_parity.py`
- Create: `backend/tests/integration/test_parity_profile_generation.py`
- Create: `backend/tests/integration/test_parity_report_tools.py`
- Create: `backend/tests/integration/test_parity_simulation_prepare.py`
- Create: `backend/tests/integration/test_parity_simulation_run.py`
- Create: `backend/tests/integration/test_parity_multilingual_flow.py`

**Step 1: Write the failing test**

```python
from backend.app.parity_engine.evaluator import DownstreamParityEvaluator


def test_downstream_parity_evaluator_compares_profile_and_report_outputs():
    evaluator = DownstreamParityEvaluator()
    report = evaluator.compare(
        zep_profile={"facts": ["a"]},
        local_profile={"facts": ["a"]},
        zep_report={"tool_results": ["x"]},
        local_report={"tool_results": ["x"]},
    )
    assert "profile_score" in report
    assert "report_score" in report
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/parity_engine/test_downstream_parity.py -q`

Expected: FAIL because evaluator does not exist

**Step 3: Write minimal implementation**

Build a harness that compares:

- `OasisProfileGenerator` outputs
- `prepare_simulation` success and generated files
- simulation start/run status/stop behavior
- `ReportAgent` tool outputs
- report generation and chat responses
- memory update effect on later searches

This harness must score:

- profile completeness
- report tool usefulness
- simulation prepare success
- simulation run parity
- memory update retrievability
- Korean/English flow parity

**Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/parity_engine/test_downstream_parity.py backend/tests/integration/test_parity_profile_generation.py backend/tests/integration/test_parity_report_tools.py backend/tests/integration/test_parity_simulation_prepare.py backend/tests/integration/test_parity_simulation_run.py backend/tests/integration/test_parity_multilingual_flow.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/parity_engine/evaluator.py backend/tests/parity_engine/test_downstream_parity.py backend/tests/integration/test_parity_profile_generation.py backend/tests/integration/test_parity_report_tools.py backend/tests/integration/test_parity_simulation_prepare.py backend/tests/integration/test_parity_simulation_run.py backend/tests/integration/test_parity_multilingual_flow.py
git commit -m "feat: add downstream parity harness"
```

### Task 9: Runtime Backend Modes and Optional Shadow Evaluation

**Files:**
- Create: `backend/app/parity_engine/shadow_eval.py`
- Modify: `backend/app/config.py`
- Modify: `backend/run.py`
- Create: `backend/tests/integration/test_shadow_eval_mode.py`

**Step 1: Write the failing test**

```python
from app.config import Config


def test_shadow_eval_mode_is_supported(monkeypatch):
    monkeypatch.setenv("GRAPH_BACKEND", "shadow_eval")
    assert "shadow_eval" == Config.GRAPH_BACKEND
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/integration/test_shadow_eval_mode.py -q`

Expected: FAIL because config/runtime does not support shadow eval

**Step 3: Write minimal implementation**

Implement `GRAPH_BACKEND` modes:

- `zep`
- `shadow_eval`
- `local_primary`

Behavior:

- `zep`: current production path
- `shadow_eval`: optional diagnostic mode. Zep remains source of truth, Graphiti-backed engine runs sidecar and stores parity scorecards only
- `local_primary`: Graphiti-backed engine becomes source of truth, Zep optional fallback disabled

Add engine connection settings:

- `ENGINE_BASE_URL=http://127.0.0.1:8123`
- `ENGINE_TIMEOUT_SECONDS`
- `ENGINE_SHADOW_EVAL_ENABLED`
- `ENGINE_DEFAULT_PORT=8123`

**Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/integration/test_shadow_eval_mode.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/parity_engine/shadow_eval.py backend/app/config.py backend/run.py backend/tests/integration/test_shadow_eval_mode.py
git commit -m "feat: add shadow evaluation runtime mode"
```

### Task 10: `zep_cloud` Compatibility Adapter and Final Cutover

**Files:**
- Create: `backend/bootstrap_graph_backend.py`
- Create: `backend/shims/local_zep/zep_cloud/__init__.py`
- Create: `backend/shims/local_zep/zep_cloud/client.py`
- Create: `backend/shims/local_zep/zep_cloud/external_clients/ontology.py`
- Create: `backend/shims/local_zep/zep_cloud/_adapter.py`
- Create: `backend/tests/integration/test_local_primary_adapter.py`
- Create: `backend/tests/integration/test_local_primary_bootstrap.py`
- Create: `backend/tests/integration/test_existing_graph_id_coexistence.py`
- Modify: `backend/run.py`
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `README-EN.md`
- Modify: `README-ZH.md`

**Step 1: Write the failing test**

```python
def test_local_primary_adapter_exposes_zep_contract(monkeypatch, tmp_path):
    monkeypatch.setenv("GRAPH_BACKEND", "local_primary")
    monkeypatch.setenv("ENGINE_BASE_URL", "http://127.0.0.1:8123")

    from zep_cloud.client import Zep

    client = Zep(api_key="__local__")
    assert hasattr(client.graph, "search")
    assert hasattr(client.graph.node, "get_by_graph_id")
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/integration/test_local_primary_adapter.py -q`

Expected: FAIL because compatibility adapter does not exist

**Step 3: Write minimal implementation**

Build the adapter only after Tasks 1-9 are green.

The adapter must:

- translate `zep_cloud` contract calls into HTTP calls to the parity engine service
- expose field-compatible node/edge/episode/search objects
- preserve `graph_id` and state/output shape expected by existing services
- preserve package-level symbols imported by existing code: `EpisodeData`, `EntityEdgeSourceTarget`, `InternalServerError`, `EntityModel`, `EntityText`, `EdgeModel`
- support both `client.graph.node.get_edges(...)` and the older `client.graph.node.get_entity_edges(...)` call shape expected by current MiroFish code
- enforce or normalize live-observed ontology constraints such as required descriptions and `SCREAMING_SNAKE_CASE` edge names

Also add bootstrap/import-hook wiring:

- `backend/bootstrap_graph_backend.py`
- local or shadow modes must prepend the compatibility package before existing `zep_cloud` imports execute
- `backend/run.py` must activate this bootstrap before importing `app`
- integration tests must prove that existing service modules import unchanged while resolving to the engine-backed adapter in `local_primary`
- add import/migration handling for existing graph/project identifiers created before local cutover

Also document:

- `pip install -r requirements.txt`
- `python app.py`
- engine port `8123`
- `GRAPH_BACKEND=zep`
- `GRAPH_BACKEND=shadow_eval`
- `GRAPH_BACKEND=local_primary`
- `ENGINE_BASE_URL`
- `ENGINE_HOST`
- `ENGINE_PORT`
- `GRAPHITI_BACKEND`
- `GRAPHITI_DB_PATH`
- `GRAPHITI_LLM_*`
- `GRAPHITI_EMBEDDING_*`
- `GRAPHITI_RERANK_*`
- `GRAPHITI_DEFAULT_LANGUAGES`
- `GRAPHITI_STDOUT_LOGGING`
- cutover requires scorecards above thresholds

**Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/integration/test_local_primary_adapter.py backend/tests/integration/test_local_primary_bootstrap.py backend/tests/integration/test_existing_graph_id_coexistence.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/bootstrap_graph_backend.py backend/run.py backend/shims/local_zep/zep_cloud backend/tests/integration/test_local_primary_adapter.py backend/tests/integration/test_local_primary_bootstrap.py backend/tests/integration/test_existing_graph_id_coexistence.py .env.example README.md README-EN.md README-ZH.md
git commit -m "feat: add graphiti-backed parity adapter"
```

## Rollout Rules

- Never switch directly from `zep` to `local_primary`.
- Only enable `local_primary` when scorecards pass thresholds and hard compatibility gates pass.
- Authoritative parity evidence must be produced from a provider-backed local candidate capture.
- `GRAPHITI_EPISODE_INLINE=true` or other inline/debug captures are non-authoritative and must not be used for cutover approval.
- Engine service itself must always be launchable independently via `python app.py` during all rollout stages.

## Final Acceptance Criteria

- Golden corpus scorecards meet all thresholds.
- The golden corpus comparison must use a provider-backed local candidate capture, not an inline/debug capture.
- `local_primary` mode passes:
  - graph build flows
  - entity read flows
  - search flows
  - profile generation flows
  - report generation/chat/statistics flows
  - simulation prepare and graph memory update flows
- existing graph/project assets import or migrate successfully and preserve compatibility guarantees
- Existing MiroFish services operate without business logic rewrites.
- Engine runtime is pip-only, starts with `python app.py`, and listens on `8123` by default.
- Hard compatibility gates all pass with backend still on `5001` and engine on `8123`.

## Execution Handoff

이 계획은 현재 세션에서 `superpowers:subagent-driven-development`로 실행하는 것을 전제로 작성됐다. 다만 adapter 작업은 마지막 task이고, 그 전까지는 parity corpus, baseline capture, Graphiti-backed engine, evaluation harness 작업이 주가 된다.

Plan complete and saved to `docs/plans/2026-03-14-zep-compatible-local-backend.md`.

Two execution options:

**1. Subagent-Driven (this session)** - fresh subagent per task, task별 spec review 후 code quality review

**2. Parallel Session (separate)** - 새 세션에서 `executing-plans`로 parity engine task를 배치 실행

Which approach?

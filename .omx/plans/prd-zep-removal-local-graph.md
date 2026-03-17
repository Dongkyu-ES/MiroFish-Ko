# PRD: ZEP 제거 및 로컬 그래프 백엔드 전환

## Current Status
- **상태:** 핵심 저장/조회 파이프라인 1차 완료
- 완료된 경로:
  - local graph repository 도입
  - local graph build
  - local entity reader
  - local search/statistics
  - local graph memory update
- live smoke 성공:
  - local graph build 완료
  - `/api/simulation/generate-profiles` local graph 기반 성공
  - `/api/report/tools/search` 성공
  - `/api/report/tools/statistics` 성공
  - local memory updater 직접 smoke 성공
- `report generate`도 local graph 기준으로 시작되어 outline 생성 및 section generation 진입까지 확인됨

## Requirements Summary
- 현재 그래프 구축/조회/검색/메모리 업데이트는 ZEP Cloud에 강하게 결합돼 있다 (`backend/app/services/graph_builder.py`, `backend/app/services/zep_entity_reader.py`, `backend/app/services/zep_tools.py`, `backend/app/services/zep_graph_memory_updater.py`).
- Codex CLI 전환은 완료됐지만, 전체 E2E는 ZEP 인증 실패 시 막힌다.
- 목표는 ZEP를 제거하고 **로컬 그래프 저장소 + Codex 추론 계층**으로 전환하는 것이다.

## Decision
1. ZEP를 바로 전부 제거하지 않고, 먼저 **로컬 그래프 저장소(repository) 계층**을 도입한다.
2. 1차 구현은 **SQLite 기반 로컬 그래프 메타/노드/엣지 저장소**를 만든다.
3. 이후 `graph_builder.py` → `zep_entity_reader.py`/`zep_tools.py` → `zep_graph_memory_updater.py` 순으로 로컬 저장소를 연결한다.

## Scope
### In Scope
- 진행 목록/교체 순서 문서화
- `GRAPH_BACKEND`, `LOCAL_GRAPH_DB_PATH` 설정 추가
- SQLite 기반 `LocalGraphRepository` 추가
- repository 수준 테스트 추가

### Out of Scope (현재도 남음)
- 실제 `graph_builder.py` 교체
- 로컬 검색/통계 로직 연결
- 시뮬레이션 후 메모리 업데이트 연결

## Acceptance Criteria
1. 로컬 그래프 저장소가 그래프 메타데이터를 생성/조회/삭제할 수 있다.
2. 온톨로지를 graph 단위로 저장/조회할 수 있다.
3. 노드/엣지 snapshot을 저장 후 다시 읽을 수 있다.
4. 그래프 정보(`node_count`, `edge_count`, `entity_types`)를 계산할 수 있다.
5. pytest로 repository 동작이 검증된다.

## Worklist

### Phase 1 — 로컬 저장소 도입
**상태: 완료**
1. `backend/app/config.py`
   - `GRAPH_BACKEND`
   - `LOCAL_GRAPH_DB_PATH`
2. `backend/app/services/local_graph_repository.py`
   - schema init
   - graph create/get/delete
   - ontology save/load
   - node/edge snapshot save/load
   - graph info 계산
3. `backend/tests/test_local_graph_repository.py`

### Phase 2 — 그래프 구축 경로 교체
**상태: 완료(1차 local build path)**
1. `backend/app/services/graph_builder.py`
2. `backend/app/api/graph.py`

### Phase 3 — 조회/검색 경로 교체
**상태: 완료(1차)**
1. `backend/app/services/zep_entity_reader.py`
2. `backend/app/services/zep_tools.py`

### Phase 4 — 메모리 업데이트 경로 교체
**상태: 완료(1차)**
1. `backend/app/services/zep_graph_memory_updater.py`

### Phase 5 — ZEP 의존 제거
**상태: 부분 완료**
1. `backend/requirements.txt`
2. `backend/pyproject.toml`
3. `.env.example`

## Completed Evidence
- repository/unit tests: `backend/tests/test_local_graph_repository.py`
- live local build smoke: graph 생성/조회 완료
- live local reader smoke: `/api/simulation/generate-profiles` 성공
- live local tool smoke: `/api/report/tools/search`, `/api/report/tools/statistics` 성공
- live local memory smoke: `FOLLOW`, `CREATE_POST` action 반영 확인

## Remaining Gaps
- 서비스 클래스 이름/역할은 아직 `Zep*` 명칭을 유지하는 경우가 많다.
- `GRAPH_BACKEND=zep` 경로와 공존하는 과도기 상태라 import 수준에서 zep 관련 코드가 남아 있다.
- simulation prepare/start/report의 전체 장기 E2E 완주 증거는 아직 부족하다.
- local graph 검색 품질은 현재 simple lexical/local heuristic 중심이다.

## Risks and Mitigations
- **리스크:** ZEP가 자동으로 해주던 graph extraction 품질이 떨어질 수 있다.  
  **대응:** 저장소 계층과 extraction 계층을 분리하고, extraction은 후속 slice에서 Codex 기반으로 대체.
- **리스크:** 조회 API와 기존 프런트 기대 포맷이 달라질 수 있다.  
  **대응:** local repository에서 기존 graph data shape에 맞는 serializer 제공.

## Verification Steps
1. pytest로 repository create/save/load/delete 검증
2. compileall 통과
3. local build smoke
4. local reader/search/stat/memory smoke

## Next Execution Slice
1. `report generate` 완료까지의 안정화 검증
2. `prepare` / `start` / `graph_memory_update_enabled` 경로 local graph 기준 심화 검증
3. 남은 ZEP 명명/조건부 import 정리

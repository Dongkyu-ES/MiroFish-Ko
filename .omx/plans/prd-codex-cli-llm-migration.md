# PRD: Codex CLI 기반 LLM 계층 전환

## Current Status
- **상태:** 대부분 완료
- 공용 LLM 계층은 `CodexBroker` 기반으로 전환되었고, backend 런타임은 Codex CLI 전용으로 정리됐다.
- 다음 경로가 공용 Codex 계층을 사용하도록 전환 완료:
  - `backend/app/services/ontology_generator.py`
  - `backend/app/services/simulation_config_generator.py`
  - `backend/app/services/oasis_profile_generator.py`
  - `backend/app/services/report_agent.py`
  - `backend/app/services/zep_tools.py`
- live smoke 완료:
  - `LLMClient.chat_json()` → Codex JSON lane 성공
  - `LLMClient.chat()` → Codex reasoning lane 성공
  - Flask 앱 부팅 + `/health` 성공
  - `/api/graph/ontology/generate` 성공
- OpenAI 호환 fallback runtime path와 backend dependency는 제거되었다.

## Requirements Summary
- 목표는 OpenAI 호환 API 키 호출 계층을 Codex CLI 기반 실행 계층으로 점진 전환해 **추가 API 과금 의존성을 제거**하는 것이다.
- 현재 LLM 설정은 OpenAI 호환 전제를 두고 있다 (`backend/app/config.py:30-33`).
- 공용 LLM 래퍼는 `LLMClient` 하나로 집중돼 있고, 대부분의 고수준 생성/추론 경로가 이를 사용한다 (`backend/app/utils/llm_client.py:17-100`).
- 보고서/그래프 툴 계층은 공용 래퍼 의존이 강하다 (`backend/app/services/report_agent.py:817,1088,1215,1418,1739,1779`, `backend/app/services/zep_tools.py:424,435,438,1124,1581,1639,1689`).
- 일부 핵심 생성 경로는 아직 `OpenAI` 클라이언트를 직접 생성한다 (`backend/app/services/oasis_profile_generator.py:18,195`, `backend/app/services/simulation_config_generator.py:22,239`).
- 기존 UI/API는 이미 polling 기반 장기 작업 패턴을 사용하므로, Codex 전환도 같은 상호작용 모델을 유지하는 것이 현실적이다 (`backend/app/api/graph.py:251-318`, `backend/app/api/simulation.py:358-425`, `backend/app/api/report.py:24-91`).

## Problem Statement
현재 구조는 “빠른 JSON 응답 = OpenAI 호환 API”를 가정한다. 이 방식은 비용 통제가 어렵고, Codex CLI 기반 운영 목표와 충돌한다. 하지만 한 번에 모든 호출 지점을 직접 `codex exec`로 바꾸면 응답 형식 안정성, 재시도, 디버깅, 장기 작업 추적이 무너질 가능성이 높다. 따라서 **공용 브로커를 먼저 도입하고, 호출 지점을 현실적인 순서로 흡수**해야 한다.

## Decision
1. **1차 목표**는 `CodexBroker`와 provider switch를 도입해 공용 래퍼를 Codex CLI 뒤로 숨기는 것이다.
2. **2차 목표**는 공용 래퍼를 사용하는 경로부터 Codex로 전환하고, 직접 `OpenAI`를 생성하는 두 서비스는 후속 단계에서 브로커로 흡수한다.
3. **3차 목표**는 장기적으로 JSON lane / reasoning lane / async task lane을 분리해 전체 전환을 완성한다.

## Scope
### In Scope
- `LLM_PROVIDER` 기반 provider 전환
- `CodexBroker` 추가
- 공용 `LLMClient`를 Codex-aware wrapper로 개편
- Codex 실행 산출물 저장 디렉터리 추가
- `.env.example`에 Codex 설정 문서화
- 최소 단위 자동 테스트 추가

### Out of Scope (현재도 남음)
- `oasis_profile_generator.py` 직접 전환
- `simulation_config_generator.py` 직접 전환
- `report_agent.py` 구조 분해
- async worker / background queue 전면 도입

## Acceptance Criteria
1. `LLM_PROVIDER=codex_cli`일 때 `Config.validate()`가 `LLM_API_KEY`를 필수로 요구하지 않는다.
2. `LLMClient.chat()`/`chat_json()`은 호출부 변경 없이 Codex CLI 기반으로 실행 가능하다.
3. Codex JSON lane은 `gpt-5.4-mini`, reasoning lane은 `gpt-5.4`를 기본값으로 분리한다.
4. Codex 실행 요청/출력/오류는 파일로 남아 재현 가능해야 한다.
5. OpenAI provider 경로는 기존 동작을 유지해야 한다.
6. 새 테스트가 provider routing의 기본 회귀를 잡아야 한다.

## Implementation Plan

### Phase 1 — 공용 브로커/설정 도입
**상태: 완료**
1. `backend/app/config.py`
   - `LLM_PROVIDER`
   - `CODEX_BIN`
   - `CODEX_JSON_MODEL`
   - `CODEX_REASONING_MODEL`
   - `CODEX_*_REASONING_EFFORT`
   - `CODEX_SERVICE_TIER`
   - `CODEX_SANDBOX`
   - `CODEX_TASKS_DIR`
   추가
2. `backend/app/utils/codex_broker.py`
   - `codex exec` 호출 래퍼 추가
   - text/json lane 분리
   - task artifact 저장
3. `backend/app/utils/llm_client.py`
   - provider switch 도입
   - OpenAI / CodexBroker 라우팅
4. `.env.example`
   - Codex 전환용 예시 변수 추가
5. `backend/tests/*`
   - provider routing 테스트 추가

### Phase 2 — 직접 OpenAI 호출 제거
**상태: 완료**
1. `backend/app/services/simulation_config_generator.py`
2. `backend/app/services/oasis_profile_generator.py`
3. 필요 시 공통 prompt/schema builder 분리

### Phase 3 — Report/Tool 계층 전환
**상태: 완료(1차 lane 분리까지)**
1. `backend/app/services/report_agent.py`
2. `backend/app/services/zep_tools.py`
3. section별 reasoning / tool summary lane 분리

### Phase 4 — 장기 작업화/비동기화
**상태: 미완**
1. Codex async task manager 추가
2. `prepare`, `report generate`, `interview` 경로의 장기 작업화
3. 재시작 복구 가능한 task persistence 강화

## Completed Evidence
- 단위 테스트: `backend/tests/test_llm_client_provider.py`
- 검증 결과: Codex provider 관련 테스트 green
- 수동 smoke:
  - `chat_json` live success
  - `chat` live success
  - `ontology/generate` live success

## Remaining Gaps
- `report generate`는 local graph 기준으로 실제 실행이 시작되고 섹션 생성 진입까지 확인했으나, 최종 completed까지의 장시간 smoke 증거는 아직 없다.
- async orchestration/task persistence 개선은 아직 미진행이다.
- Codex 호출량/지연 최적화는 아직 후속 과제다.

## Risks and Mitigations
- **리스크:** `codex exec` 응답 형식이 JSON-only를 깨뜨릴 수 있다.  
  **대응:** `--output-schema` + JSON parse + 실패 시 명확한 예외 처리.
- **리스크:** Codex CLI 미설치/로그인 만료 시 서버가 부팅 후 실패할 수 있다.  
  **대응:** `Config.validate()`에 provider별 사전 검증 추가.
- **리스크:** 직접 `OpenAI` 사용 서비스는 여전히 과금 경로가 남는다.  
  **대응:** 이번 단계에서 “공용 래퍼 전환 완료, 직접 호출 서비스는 Phase 2 대상”으로 명시.
- **리스크:** Codex CLI 호출은 지연이 커서 기존 sync path에서 병목이 생길 수 있다.  
  **대응:** 이번 단계는 sync adapter만 도입하고, 다음 단계에서 async lane으로 분리.

## Verification Steps
1. unit test:
   - OpenAI provider 유지
   - Codex provider routing
2. static validation:
   - Python import/compile 확인
3. manual smoke:
   - `.env`에서 `LLM_PROVIDER=codex_cli` 설정 후 앱 부팅 시 validate 통과 확인
4. artifact check:
   - Codex 호출 시 `backend/uploads/codex_tasks/*` 생성 확인

## File Impact
- `backend/app/config.py`
- `backend/app/utils/llm_client.py`
- `backend/app/utils/codex_broker.py`
- `.env.example`
- `backend/tests/test_llm_client_provider.py`

## Next Execution Slice
이 PRD 기준 남은 실질 작업은:
1. `report generate` 완료까지의 안정화 검증
2. `prepare/report/interview` 장기 작업 비동기 최적화
3. Codex task persistence/재개 전략 보강

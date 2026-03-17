# Test Spec: Codex CLI 기반 LLM 계층 전환

## Test Strategy Summary
- 1차 전환은 **공용 provider 계층 안정화**가 핵심이다.
- 따라서 이번 테스트는 E2E보다 **provider routing / 설정 검증 / artifact 생성 가능성**에 집중한다.

## Test Matrix

### A. Config validation
1. `LLM_PROVIDER=openai_compat`
   - `LLM_API_KEY` 없으면 validate 실패
2. `LLM_PROVIDER=codex_cli`
   - `LLM_API_KEY` 없어도 validate 통과
   - `codex` 실행 파일이 없으면 validate 실패

### B. LLMClient routing
1. OpenAI provider
   - `chat_json()`가 기존 markdown fenced JSON을 파싱 가능해야 함
2. Codex provider
   - `chat_json()`가 `CodexBroker.chat_json()`으로 위임되어야 함
   - `chat()`가 `CodexBroker.chat()`으로 위임되어야 함

### C. CodexBroker behavior
1. text lane
   - `codex exec` 명령이 reasoning model로 구성되어야 함
2. json lane
   - `codex exec --output-schema`가 포함되어야 함
   - output file의 JSON object를 dict로 파싱해야 함
3. artifact
   - `request.json`
   - `prompt.txt`
   - `result.json` 또는 `result.txt`
   - `stdout.log`
   - `stderr.log`
   저장돼야 함

## Manual Smoke Plan
1. `.env`에 아래 설정
   - `LLM_PROVIDER=codex_cli`
   - `CODEX_JSON_MODEL=gpt-5.3-codex-spark`
   - `CODEX_REASONING_MODEL=gpt-5.4`
2. Flask 부팅
3. 간단한 Python shell 또는 단위 API에서 `LLMClient.chat_json()` 호출
4. 산출물 디렉터리 확인

## Non-Goals for This Slice
- `report_agent.py`의 section generation 품질 검증
- OASIS profile batch 생성 성능 검증
- 시뮬레이션 전체 E2E 무중단 검증

## Exit Criteria
1. 새 unit tests 통과
2. Python compile/import 통과
3. Codex provider 부팅 검증 통과
4. 문서화된 환경 변수로 동작 경로가 명확해짐

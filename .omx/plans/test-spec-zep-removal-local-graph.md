# Test Spec: 로컬 그래프 저장소 1차 도입

## Current Status
- repository tests green
- local graph builder tests green
- local reader/search/stat tests green
- local memory updater tests green
- live smoke로 build / generate-profiles / report tools / memory update 확인
- live smoke로 prepare ready 확인
- live smoke로 report generate completed 확인
- live smoke로 start + graph_memory_update_enabled completed 및 graph edge 증가 확인
- graph-oriented naming cleanup 시작(compat alias 유지)

## Test Matrix

### A. Graph metadata
1. graph 생성 시 id/name/description 저장
2. graph 조회 시 동일 값 반환
3. graph 삭제 시 관련 데이터도 함께 제거

### B. Ontology persistence
1. ontology 저장
2. 저장 후 동일 ontology 반환

### C. Snapshot persistence
1. nodes/edges 저장
2. 저장 후 graph data 반환
3. graph info 계산 시:
   - node_count 정확
   - edge_count 정확
   - `Entity`/`Node` 제외 entity_types 계산

### D. Isolation
1. graph A/B 데이터가 섞이지 않아야 함

### E. Runtime integration
1. local graph build가 task 완료까지 진행되어야 함
2. local reader가 simulation profile generation에 사용 가능해야 함
3. local search/stat API가 report tool endpoint에서 동작해야 함
4. local memory updater가 action batch를 graph edge로 적재해야 함
5. local prepare가 ready/completed까지 도달해야 함
6. local report generate가 completed까지 도달해야 함
7. local start + graph_memory_update_enabled가 completed까지 도달하고 graph edge 증가가 관측돼야 함

## Exit Criteria
1. repository 테스트 green
2. compileall green
3. 최소 local build smoke green
4. 최소 reader/search/stat/memory smoke green
5. prepare smoke green
6. report completed smoke green
7. start + graph memory smoke green
8. 문서화된 다음 slice 준비 완료

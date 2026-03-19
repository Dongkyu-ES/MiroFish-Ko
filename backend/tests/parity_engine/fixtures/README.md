# Parity Corpus Fixtures

이 디렉터리는 SSOT 문서에 정의된 v1 parity corpus의 canonical manifest를 보관한다.

## Canonical Cases

- `ko_alias_case`: 한국어 alias-heavy entity normalization
- `en_temporal_case`: English temporal fact lifecycle
- `ko_report_case`: 한국어 report generation/tool usefulness
- `en_profile_case`: English profile completeness
- `sim_memory_case`: simulation memory ingestion and retrieval

## Contract Rules

- 각 corpus item은 입력 문서 경로를 선언해야 한다.
- 각 corpus item은 `ontology_mode`로 ontology input 또는 generation mode를 선언해야 한다.
- 각 corpus item은 parity search query 집합을 선언해야 한다.
- 각 corpus item은 실행해야 할 downstream flow를 `expected_outputs`로 선언해야 한다.

## Artifact Layout

Task 2 이후 baseline golden artifacts는 아래 경로를 따른다.

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

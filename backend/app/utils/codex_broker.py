"""
Codex CLI 기반 LLM 브로커.

공용 LLM 호출부가 OpenAI 호환 API에 직접 결합되지 않도록
`codex exec` 호출을 감싸는 얇은 브로커 계층을 제공합니다.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..config import Config
from .logger import get_logger

logger = get_logger('mirofish.codex_broker')

RATE_LIMIT_PATTERNS = (
    "usage limit",
    "rate limit",
    "hit your usage limit",
)


class CodexBroker:
    """Codex CLI 호출 래퍼."""

    TASK_DIR_MAX_AGE_SEC = 3600  # 1시간
    _CLEANUP_INTERVAL_SEC = 300  # 5분마다 최대 1회 정리
    _last_cleanup_time: float = 0.0

    def __init__(
        self,
        codex_bin: Optional[str] = None,
        workdir: Optional[str] = None,
        tasks_dir: Optional[str] = None,
        json_model: Optional[str] = None,
        reasoning_model: Optional[str] = None,
        json_reasoning_effort: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
        service_tier: Optional[str] = None,
        sandbox: Optional[str] = None,
    ):
        self.codex_bin = codex_bin or Config.CODEX_BIN
        self.workdir = Path(workdir) if workdir else Path(__file__).resolve().parents[3]
        self.tasks_dir = Path(tasks_dir or Config.CODEX_TASKS_DIR)
        self.json_model = json_model or Config.CODEX_JSON_MODEL
        self.reasoning_model = reasoning_model or Config.CODEX_REASONING_MODEL
        self.json_reasoning_effort = json_reasoning_effort or Config.CODEX_JSON_REASONING_EFFORT
        self.reasoning_effort = reasoning_effort or Config.CODEX_REASONING_EFFORT
        self.service_tier = service_tier or Config.CODEX_SERVICE_TIER
        self.sandbox = sandbox or Config.CODEX_SANDBOX
        
        self.tasks_dir.mkdir(parents=True, exist_ok=True)

    def cleanup_old_tasks(self):
        """TASK_DIR_MAX_AGE_SEC보다 오래된 태스크 디렉터리를 삭제한다. _CLEANUP_INTERVAL_SEC마다 최대 1회 실행."""
        import shutil
        now = time.time()
        if now - CodexBroker._last_cleanup_time < self._CLEANUP_INTERVAL_SEC:
            return 0
        CodexBroker._last_cleanup_time = now
        removed = 0
        if not self.tasks_dir.exists():
            return 0
        for entry in self.tasks_dir.iterdir():
            if entry.is_dir():
                try:
                    age = now - entry.stat().st_mtime
                    if age > self.TASK_DIR_MAX_AGE_SEC:
                        shutil.rmtree(entry)
                        removed += 1
                except OSError:
                    pass
        if removed:
            logger.info(f"오래된 태스크 디렉터리 {removed}개 삭제: {self.tasks_dir}")
        return removed

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        del temperature, max_tokens  # Codex CLI lane에서는 현재 미사용
        return self.run_reasoning_task(
            task_name='chat',
            messages=messages,
            timeout_sec=Config.CODEX_TIMEOUT_REASONING_SEC,
        )
    
    def chat_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        schema: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        del temperature, max_tokens  # Codex CLI lane에서는 현재 미사용
        return self.run_json_task(
            task_name='chat_json',
            messages=messages,
            schema=schema,
            timeout_sec=Config.CODEX_TIMEOUT_JSON_SEC,
        )
    
    def run_reasoning_task(
        self,
        task_name: str,
        messages: List[Dict[str, str]],
        timeout_sec: int,
    ) -> str:
        self.cleanup_old_tasks()
        prompt = self._messages_to_prompt(messages, expect_json=False)
        task_dir = self._create_task_dir(task_name)
        output_file = task_dir / 'result.txt'
        request_payload = {
            'lane': 'reasoning',
            'task_name': task_name,
            'model': self.reasoning_model,
            'reasoning_effort': self.reasoning_effort,
            'service_tier': self.service_tier,
            'timeout_sec': timeout_sec,
            'messages': messages,
        }
        self._write_request_artifacts(task_dir, prompt, request_payload)
        
        command = self._build_base_command(
            model=self.reasoning_model,
            reasoning_effort=self.reasoning_effort,
            output_file=output_file,
        )
        self._run_command_with_fallback(
            command=command,
            prompt=prompt,
            task_dir=task_dir,
            timeout_sec=timeout_sec,
            output_file=output_file,
            fallback_model="gpt-5.4-mini",
            fallback_effort="low",
            fallback_model_2="gpt-5-nano",
            fallback_effort_2="low",
            messages=messages,
            expect_json=False,
        )
        return output_file.read_text(encoding='utf-8').strip()
    
    def run_json_task(
        self,
        task_name: str,
        messages: List[Dict[str, str]],
        schema: Optional[Dict[str, Any]],
        timeout_sec: int,
    ) -> Dict[str, Any]:
        self.cleanup_old_tasks()
        prompt = self._messages_to_prompt(messages, expect_json=True)
        task_dir = self._create_task_dir(task_name)
        output_file = task_dir / 'result.json'
        schema_file = None
        schema_payload = schema
        if schema_payload is not None:
            schema_file = task_dir / 'schema.json'
            schema_file.write_text(json.dumps(schema_payload, ensure_ascii=False, indent=2), encoding='utf-8')
        
        request_payload = {
            'lane': 'json',
            'task_name': task_name,
            'model': self.json_model,
            'reasoning_effort': self.json_reasoning_effort,
            'service_tier': self.service_tier,
            'timeout_sec': timeout_sec,
            'messages': messages,
            'schema': schema_payload,
        }
        self._write_request_artifacts(task_dir, prompt, request_payload)
        
        command = self._build_base_command(
            model=self.json_model,
            reasoning_effort=self.json_reasoning_effort,
            output_file=output_file,
            schema_file=schema_file,
        )
        self._run_command_with_fallback(
            command=command,
            prompt=prompt,
            task_dir=task_dir,
            timeout_sec=timeout_sec,
            output_file=output_file,
            fallback_model="gpt-5.4-mini",
            fallback_effort="low",
            fallback_model_2="gpt-5-nano",
            fallback_effort_2="low",
            messages=messages,
            expect_json=True,
        )
        
        try:
            return self._parse_json_output(output_file.read_text(encoding='utf-8'))
        except json.JSONDecodeError as exc:
            repaired = self._repair_json_via_codex(
                raw_output=output_file.read_text(encoding='utf-8'),
                task_dir=task_dir,
                timeout_sec=timeout_sec,
            )
            try:
                return self._parse_json_output(repaired)
            except json.JSONDecodeError as repair_exc:
                raise ValueError(f"Codex JSON 결과 파싱 실패: {repair_exc}") from exc
    
    def _build_base_command(
        self,
        model: str,
        reasoning_effort: str,
        output_file: Path,
        schema_file: Optional[Path] = None,
    ) -> List[str]:
        command = [
            self.codex_bin,
            'exec',
            '--skip-git-repo-check',
            '--sandbox', self.sandbox,
            '-C', str(self.workdir),
            '-m', model,
            '-c', f'model_reasoning_effort="{reasoning_effort}"',
            '-c', f'service_tier="{self.service_tier}"',
            '--output-last-message', str(output_file),
        ]
        if schema_file:
            command.extend(['--output-schema', str(schema_file)])
        command.append('-')
        return command

    @staticmethod
    def _extract_json_from_text(text: str) -> str:
        """텍스트에서 JSON 객체만 추출. 마크다운 펜스/설명문 제거."""
        cleaned = text.strip()
        # 마크다운 펜스 제거
        cleaned = re.sub(r'^```(?:json)?\s*\n?', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\n?```\s*$', '', cleaned)
        # 첫 번째 '{' 부터 마지막 '}' 까지 추출
        first_brace = cleaned.find('{')
        last_brace = cleaned.rfind('}')
        if first_brace != -1 and last_brace > first_brace:
            cleaned = cleaned[first_brace:last_brace + 1]
        return cleaned

    def _parse_json_output(self, raw_text: str) -> Dict[str, Any]:
        cleaned = self._extract_json_from_text(raw_text)
        return json.loads(cleaned)

    def _repair_json_via_codex(self, raw_output: str, task_dir: Path, timeout_sec: int) -> str:
        repair_prompt = (
            "[SYSTEM]\n"
            "You repair malformed JSON. Return only valid JSON with the same intended structure. "
            "Do not add markdown fences.\n\n"
            "[USER]\n"
            f"The following output is intended to be JSON but is malformed. Repair it:\n{raw_output}"
        )
        repair_output = task_dir / 'result_repaired.json'
        (task_dir / 'repair_prompt.txt').write_text(repair_prompt, encoding='utf-8')

        # Claude 우선 모드일 때 Claude로 repair 시도
        if Config.CLAUDE_FALLBACK_ENABLED and getattr(Config, 'CLAUDE_PRIMARY', False):
            try:
                self._call_claude(
                    prompt=repair_prompt,
                    task_dir=task_dir,
                    output_file=repair_output,
                    model=Config.CLAUDE_MODEL_FAST,
                )
                return repair_output.read_text(encoding='utf-8')
            except RuntimeError:
                logger.warning("Claude repair 실패, Codex CLI로 폴백")

        command = self._build_base_command(
            model=self.json_model,
            reasoning_effort=self.json_reasoning_effort,
            output_file=repair_output,
        )
        self._run_command(
            command=command,
            prompt=repair_prompt,
            task_dir=task_dir,
            timeout_sec=timeout_sec,
            output_file=repair_output,
        )
        return repair_output.read_text(encoding='utf-8')

    def _run_command_with_fallback(
        self,
        command: List[str],
        prompt: str,
        task_dir: Path,
        timeout_sec: int,
        output_file: Path,
        fallback_model: Optional[str] = None,
        fallback_effort: Optional[str] = None,
        fallback_model_2: Optional[str] = None,
        fallback_effort_2: Optional[str] = None,
        messages: Optional[List[Dict[str, str]]] = None,
        expect_json: bool = False,
    ) -> None:
        # Claude 우선 모드: CLAUDE_FALLBACK_ENABLED + CLAUDE_PRIMARY
        if Config.CLAUDE_FALLBACK_ENABLED and getattr(Config, 'CLAUDE_PRIMARY', False) and messages is not None:
            logger.info("Claude 우선 모드 활성화, Claude CLI로 직접 호출")
            fallback_prompt = self._messages_to_prompt(messages, expect_json=expect_json)
            claude_model = Config.CLAUDE_MODEL_FAST if expect_json else Config.CLAUDE_MODEL_REASONING
            try:
                self._call_claude(
                    prompt=fallback_prompt,
                    task_dir=task_dir,
                    output_file=output_file,
                    model=claude_model,
                )
                return
            except RuntimeError as claude_exc:
                logger.warning("Claude 우선 호출 실패, Codex CLI로 폴백: %s", claude_exc)

        # 1차: 기본 모델 (spark 요금제)
        try:
            self._run_command(
                command=command,
                prompt=prompt,
                task_dir=task_dir,
                timeout_sec=timeout_sec,
                output_file=output_file,
            )
            return
        except RuntimeError as exc:
            error_text = str(exc).lower()
            if not fallback_model or not any(p in error_text for p in RATE_LIMIT_PATTERNS):
                raise

            # 2차: 1차 폴백 모델 (일반 요금제)
            logger.warning("Codex CLI 레이트리밋 감지, 1차 폴백 모델로 재시도: %s", fallback_model)
            fb1_command = self._build_base_command(
                model=fallback_model,
                reasoning_effort=fallback_effort or self.json_reasoning_effort,
                output_file=output_file,
            )
            try:
                self._run_command(
                    command=fb1_command,
                    prompt=prompt,
                    task_dir=task_dir,
                    timeout_sec=timeout_sec,
                    output_file=output_file,
                )
                return
            except RuntimeError as fb1_exc:
                # 3차: 2차 폴백 모델 (무료 요금제)
                if fallback_model_2:
                    logger.warning("Codex CLI 1차 폴백도 실패, 2차 폴백 모델로 재시도: %s", fallback_model_2)
                    fb2_command = self._build_base_command(
                        model=fallback_model_2,
                        reasoning_effort=fallback_effort_2 or "low",
                        output_file=output_file,
                    )
                    try:
                        self._run_command(
                            command=fb2_command,
                            prompt=prompt,
                            task_dir=task_dir,
                            timeout_sec=timeout_sec,
                            output_file=output_file,
                        )
                        return
                    except RuntimeError:
                        pass  # 3차도 실패 → Claude 폴백으로

                # 4차: Claude CLI 폴백
                if not Config.CLAUDE_FALLBACK_ENABLED or messages is None:
                    raise fb1_exc from exc
                logger.warning("Codex CLI 폴백 모두 실패, Claude CLI 최종 폴백 시도")
                fallback_prompt = self._messages_to_prompt(messages, expect_json=expect_json)
                claude_model = Config.CLAUDE_MODEL_FAST if expect_json else Config.CLAUDE_MODEL_REASONING
                self._call_claude(
                    prompt=fallback_prompt,
                    task_dir=task_dir,
                    output_file=output_file,
                    model=claude_model,
                )
    
    def _call_claude(
        self,
        prompt: str,
        task_dir: Path,
        output_file: Path,
        model: Optional[str] = None,
    ) -> None:
        claude_bin = Config.CLAUDE_BIN
        selected_model = model or Config.CLAUDE_MODEL_FAST
        command: List[str] = [
            claude_bin,
            "-p",                        # print mode (비대화형)
            "--model", selected_model,
            "--output-format", "text",   # 순수 텍스트 출력
            "--strict-mcp-config",       # --mcp-config 외 MCP 서버 무시 (로드 0개)
        ]

        (task_dir / "claude_prompt.txt").write_text(prompt, encoding="utf-8")
        logger.info(
            "Claude CLI 폴백 호출: %s, model=%s, prompt_len=%d",
            ' '.join(command), selected_model, len(prompt),
        )

        process = subprocess.run(
            command,
            input=prompt,               # stdin으로 프롬프트 전달
            text=True,
            capture_output=True,
            timeout=Config.CLAUDE_TIMEOUT_SEC,
            check=False,
        )

        (task_dir / "claude_stderr.log").write_text(process.stderr or "", encoding="utf-8")

        if process.returncode != 0:
            raise RuntimeError(
                f"Claude CLI 실행 실패(exit={process.returncode}): {(process.stderr or '').strip()}"
            )

        result_text = process.stdout.strip()
        if not result_text:
            raise RuntimeError("Claude CLI 실행은 성공했지만 출력이 비어있습니다.")

        # JSON 출력 파일이면 응답에서 JSON 객체만 추출
        if output_file.suffix == '.json':
            result_text = self._extract_json_from_text(result_text)

        output_file.write_text(result_text, encoding="utf-8")

        (task_dir / "claude_fallback.json").write_text(
            json.dumps({
                "model": selected_model,
                "bin": claude_bin,
                "finished_at": datetime.now().isoformat(),
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    
    def _run_command(
        self,
        command: List[str],
        prompt: str,
        task_dir: Path,
        timeout_sec: int,
        output_file: Optional[Path] = None,
    ) -> None:
        logger.info("Codex CLI 실행: %s", ' '.join(command[:-1]))
        process = subprocess.run(
            command,
            input=prompt,
            text=True,
            capture_output=True,
            cwd=self.workdir,
            timeout=timeout_sec,
            check=False,
        )
        (task_dir / 'stdout.log').write_text(process.stdout or '', encoding='utf-8')
        (task_dir / 'stderr.log').write_text(process.stderr or '', encoding='utf-8')
        meta = {
            'exit_code': process.returncode,
            'finished_at': datetime.now().isoformat(),
            'command': command[:-1],
        }
        (task_dir / 'meta.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
        
        if process.returncode != 0:
            raise RuntimeError(
                f"Codex CLI 실행 실패(exit={process.returncode}): {(process.stderr or process.stdout).strip()}"
            )
        expected_output = output_file or task_dir / ('result.json' if (task_dir / 'schema.json').exists() else 'result.txt')
        if not expected_output.exists():
            raise RuntimeError("Codex CLI 실행은 성공했지만 출력 파일이 생성되지 않았습니다.")
    
    def _write_request_artifacts(self, task_dir: Path, prompt: str, request_payload: Dict[str, Any]) -> None:
        (task_dir / 'prompt.txt').write_text(prompt, encoding='utf-8')
        (task_dir / 'request.json').write_text(
            json.dumps(request_payload, ensure_ascii=False, indent=2),
            encoding='utf-8',
        )
    
    def _create_task_dir(self, task_name: str) -> Path:
        task_id = f"{task_name}_{datetime.now().strftime('%Y%m%d-%H%M%S')}_{uuid.uuid4().hex[:8]}"
        task_dir = self.tasks_dir / task_id
        task_dir.mkdir(parents=True, exist_ok=False)
        return task_dir
    
    @staticmethod
    def _messages_to_prompt(messages: List[Dict[str, str]], expect_json: bool) -> str:
        parts: List[str] = []
        for message in messages:
            role = (message.get('role') or 'user').upper()
            content = message.get('content') or ''
            parts.append(f"[{role}]\n{content}".strip())
        if expect_json:
            parts.append(
                "[SYSTEM]\nIMPORTANT: Return ONLY a raw JSON object. "
                "No markdown fences, no explanation, no preamble, no trailing text. "
                "The very first character of your response must be '{' and the last must be '}'."
            )
        return '\n\n'.join(parts).strip()
    
    @staticmethod
    def _default_json_object_schema() -> Dict[str, Any]:
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "additionalProperties": True,
        }

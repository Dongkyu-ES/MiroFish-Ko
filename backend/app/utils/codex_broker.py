"""
Codex CLI 기반 LLM 브로커.

공용 LLM 호출부가 OpenAI 호환 API에 직접 결합되지 않도록
`codex exec` 호출을 감싸는 얇은 브로커 계층을 제공합니다.
"""

from __future__ import annotations

import json
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..config import Config
from .logger import get_logger

logger = get_logger('mirofish.codex_broker')


class CodexBroker:
    """Codex CLI 호출 래퍼."""
    
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
        self._run_command(
            command=command,
            prompt=prompt,
            task_dir=task_dir,
            timeout_sec=timeout_sec,
            output_file=output_file,
        )
        return output_file.read_text(encoding='utf-8').strip()
    
    def run_json_task(
        self,
        task_name: str,
        messages: List[Dict[str, str]],
        schema: Optional[Dict[str, Any]],
        timeout_sec: int,
    ) -> Dict[str, Any]:
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
        self._run_command(
            command=command,
            prompt=prompt,
            task_dir=task_dir,
            timeout_sec=timeout_sec,
            output_file=output_file,
        )
        
        try:
            return json.loads(output_file.read_text(encoding='utf-8'))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Codex JSON 결과 파싱 실패: {exc}") from exc
    
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
                "[SYSTEM]\nReturn only a valid JSON object that satisfies the provided schema. "
                "Do not wrap the JSON in markdown fences."
            )
        return '\n\n'.join(parts).strip()
    
    @staticmethod
    def _default_json_object_schema() -> Dict[str, Any]:
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "additionalProperties": True,
        }

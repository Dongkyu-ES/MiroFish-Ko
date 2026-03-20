"""
Codex CLI / Claude CLI를 통한 LLM 호출 백엔드.

camel-ai BaseModelBackend를 구현하여 API 키 없이
CLI 도구(codex, claude)를 통해 LLM을 호출합니다.
"""

import asyncio
import json
import os
import re
import subprocess
import time
import uuid
from typing import Any, Dict, List, Optional, Type, Union

from openai import AsyncStream, Stream
from pydantic import BaseModel

from camel.messages import OpenAIMessage
from camel.models import BaseModelBackend
from camel.types import (
    ChatCompletion,
    ChatCompletionChunk,
    ChatCompletionMessage,
    Choice,
    CompletionUsage,
    ModelType,
)
from camel.utils import BaseTokenCounter


class CliTokenCounter(BaseTokenCounter):
    """CLI 모델용 간단한 토큰 카운터 (len(text) // 4 근사치)."""

    def count_tokens_from_messages(self, messages: List[OpenAIMessage]) -> int:
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += len(content) // 4 + 1
        return total

    def encode(self, text: str) -> List[int]:
        return [0] * (len(text) // 4 + 1)

    def decode(self, token_ids: List[int]) -> str:
        return "[CLI decoded text]"


class CliModelBackend(BaseModelBackend):
    """Codex CLI / Claude CLI를 통한 LLM 호출 백엔드.

    API 키 없이 로컬에 설치된 CLI 도구를 사용하여
    LLM 추론을 수행합니다.

    Args:
        model_type: 모델 타입 식별자.
        cli_tool: 사용할 CLI 도구 ("codex" 또는 "claude").
            None이면 CLAUDE_PRIMARY 환경변수에 따라 결정.
        model_name: CLI에 전달할 모델 이름.
        max_concurrent: 동시 실행 제한 (asyncio.Semaphore).
        model_config_dict: 추가 모델 설정.
    """

    def __init__(
        self,
        model_type: Union[ModelType, str] = "cli-model",
        model_config_dict: Optional[Dict[str, Any]] = None,
        api_key: Optional[str] = None,
        url: Optional[str] = None,
        token_counter: Optional[BaseTokenCounter] = None,
        timeout: Optional[float] = None,
        max_retries: int = 3,
        cli_tool: Optional[str] = None,
        model_name: Optional[str] = None,
        max_concurrent: int = 8,
    ) -> None:
        super().__init__(
            model_type,
            model_config_dict,
            api_key,
            url,
            token_counter,
            timeout,
            max_retries,
        )

        # CLI 도구 결정
        if cli_tool is not None:
            self._cli_tool = cli_tool
        else:
            claude_primary = (
                os.environ.get("CLAUDE_PRIMARY", "false").lower() == "true"
            )
            self._cli_tool = "claude" if claude_primary else "codex"

        # CLI 도구별 모델명 분리
        if model_name:
            self._claude_model = model_name
            self._codex_model = model_name
        else:
            self._claude_model = os.environ.get(
                "CLAUDE_MODEL_FAST", "claude-haiku-4-5"
            )
            self._codex_model = os.environ.get(
                "CODEX_JSON_MODEL", "gpt-5.3-codex-spark"
            )
        self._model_name = (
            self._claude_model if self._cli_tool == "claude" else self._codex_model
        )
        self._semaphore = asyncio.Semaphore(max_concurrent)

    @property
    def token_counter(self) -> BaseTokenCounter:
        if not self._token_counter:
            self._token_counter = CliTokenCounter()
        return self._token_counter

    # ------------------------------------------------------------------
    # CLI 명령 빌드
    # ------------------------------------------------------------------

    def _build_cli_command(self, tool: Optional[str] = None) -> List[str]:
        """CLI 실행 명령을 구성합니다.

        Args:
            tool: "codex" 또는 "claude". None이면 인스턴스 기본값.

        Returns:
            실행할 명령 인자 리스트.
        """
        tool = tool or self._cli_tool

        if tool == "codex":
            codex_bin = os.environ.get("CODEX_BIN", "codex")
            model = self._codex_model
            return [
                codex_bin,
                "exec",
                "--skip-git-repo-check",
                "--sandbox",
                "read-only",
                "-m",
                model,
                "-",
            ]
        else:
            claude_bin = os.environ.get("CLAUDE_BIN", "claude")
            model = self._claude_model
            return [
                claude_bin,
                "-p",
                "--model",
                model,
                "--output-format",
                "text",
            ]

    # ------------------------------------------------------------------
    # 메시지 → 프롬프트 변환
    # ------------------------------------------------------------------

    def _messages_to_prompt(
        self,
        messages: List[OpenAIMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """OpenAI 메시지 형식을 텍스트 프롬프트로 변환합니다."""
        parts: List[str] = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if isinstance(content, str) and content:
                parts.append(f"[{role}]\n{content}")
            elif isinstance(content, list):
                # 멀티모달 메시지: 텍스트 부분만 추출
                text_parts = [
                    c.get("text", "")
                    for c in content
                    if isinstance(c, dict) and c.get("type") == "text"
                ]
                if text_parts:
                    parts.append(f"[{role}]\n{''.join(text_parts)}")

        prompt = "\n\n".join(parts)

        if tools:
            tool_desc = json.dumps(tools, ensure_ascii=False, indent=2)
            prompt += (
                "\n\n--- Available tools ---\n"
                f"{tool_desc}\n"
                "--- End of tools ---\n\n"
                "If you want to call a tool, respond with EXACTLY this JSON format:\n"
                '{"tool_calls": [{"function": {"name": "tool_name", '
                '"arguments": {"arg": "value"}}}]}\n'
                "If you want to respond with text, just write your response directly."
            )

        return prompt

    # ------------------------------------------------------------------
    # 응답 파싱
    # ------------------------------------------------------------------

    def _parse_response(
        self,
        text: str,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> ChatCompletion:
        """CLI 출력 텍스트를 ChatCompletion 객체로 변환합니다."""
        text = text.strip()
        tool_calls = None
        content: Optional[str] = text
        finish_reason = "stop"

        if tools:
            # JSON tool_calls 패턴 추출 시도
            tc = self._extract_tool_calls(text)
            if tc is not None:
                tool_calls = tc
                content = None
                finish_reason = "tool_calls"

        message = ChatCompletionMessage(
            content=content,
            role="assistant",
            tool_calls=tool_calls,
        )

        return ChatCompletion(
            id=f"cli-{uuid.uuid4().hex[:12]}",
            model=self._model_name,
            object="chat.completion",
            created=int(time.time()),
            choices=[
                Choice(
                    finish_reason=finish_reason,
                    index=0,
                    message=message,
                    logprobs=None,
                )
            ],
            usage=CompletionUsage(
                prompt_tokens=0,
                completion_tokens=len(text) // 4 + 1,
                total_tokens=len(text) // 4 + 1,
            ),
        )

    def _extract_tool_calls(self, text: str) -> Optional[List[Any]]:
        """텍스트에서 tool_calls JSON을 추출합니다.

        Returns:
            ChatCompletionMessageFunctionToolCall 리스트 또는 None.
        """
        from openai.types.chat.chat_completion_message_function_tool_call import (
            ChatCompletionMessageFunctionToolCall,
            Function,
        )

        # {"tool_calls": [...]} 패턴 검색
        pattern = r'\{[^{}]*"tool_calls"\s*:\s*\[.*?\]\s*\}'
        match = re.search(pattern, text, re.DOTALL)
        if not match:
            return None

        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None

        raw_calls = data.get("tool_calls")
        if not isinstance(raw_calls, list) or not raw_calls:
            return None

        result = []
        for call in raw_calls:
            func = call.get("function", {})
            name = func.get("name", "")
            arguments = func.get("arguments", {})
            if isinstance(arguments, dict):
                arguments = json.dumps(arguments, ensure_ascii=False)
            result.append(
                ChatCompletionMessageFunctionToolCall(
                    id=f"call_{uuid.uuid4().hex[:8]}",
                    function=Function(name=name, arguments=arguments),
                    type="function",
                )
            )

        return result if result else None

    # ------------------------------------------------------------------
    # 타임아웃 결정
    # ------------------------------------------------------------------

    def _get_timeout(self, tool: Optional[str] = None) -> float:
        """CLI 도구별 타임아웃(초)을 반환합니다."""
        if self._timeout is not None:
            return self._timeout
        tool = tool or self._cli_tool
        if tool == "claude":
            return float(os.environ.get("CLAUDE_TIMEOUT_SEC", "120"))
        return float(os.environ.get("CODEX_TIMEOUT_REASONING_SEC", "300"))

    # ------------------------------------------------------------------
    # _run (동기)
    # ------------------------------------------------------------------

    def _run(
        self,
        messages: List[OpenAIMessage],
        response_format: Optional[Type[BaseModel]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Union[ChatCompletion, Stream[ChatCompletionChunk]]:
        """동기 CLI 호출."""
        prompt = self._messages_to_prompt(messages, tools)
        timeout = self._get_timeout()

        # 1차 시도
        text, err = self._run_cli(self._cli_tool, prompt, timeout)
        if err is not None:
            # 폴백
            fallback = "claude" if self._cli_tool == "codex" else "codex"
            fallback_enabled = (
                os.environ.get("CLAUDE_FALLBACK_ENABLED", "true").lower()
                == "true"
            )
            if fallback_enabled:
                print(
                    f"[CliModelBackend] {self._cli_tool} 실패, "
                    f"{fallback}로 폴백: {err}"
                )
                text, err2 = self._run_cli(
                    fallback, prompt, self._get_timeout(fallback)
                )
                if err2 is not None:
                    raise RuntimeError(
                        f"CLI 백엔드 모두 실패: "
                        f"{self._cli_tool}={err}, {fallback}={err2}"
                    )
            else:
                raise RuntimeError(
                    f"CLI 백엔드 실패 ({self._cli_tool}): {err}"
                )

        return self._parse_response(text, tools)

    def _run_cli(
        self, tool: str, prompt: str, timeout: float
    ) -> tuple:
        """단일 CLI 도구를 동기 실행합니다.

        Returns:
            (stdout_text, error_or_None)
        """
        cmd = self._build_cli_command(tool)
        try:
            result = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode != 0:
                return "", f"exit {result.returncode}: {result.stderr[:500]}"
            return result.stdout, None
        except subprocess.TimeoutExpired:
            return "", f"timeout after {timeout}s"
        except FileNotFoundError:
            return "", f"{tool} binary not found"
        except Exception as exc:
            return "", str(exc)

    # ------------------------------------------------------------------
    # _arun (비동기)
    # ------------------------------------------------------------------

    async def _arun(
        self,
        messages: List[OpenAIMessage],
        response_format: Optional[Type[BaseModel]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Union[ChatCompletion, AsyncStream[ChatCompletionChunk]]:
        """비동기 CLI 호출."""
        prompt = self._messages_to_prompt(messages, tools)
        timeout = self._get_timeout()

        async with self._semaphore:
            # 1차 시도
            text, err = await self._arun_cli(self._cli_tool, prompt, timeout)
            if err is not None:
                fallback = "claude" if self._cli_tool == "codex" else "codex"
                fallback_enabled = (
                    os.environ.get("CLAUDE_FALLBACK_ENABLED", "true").lower()
                    == "true"
                )
                if fallback_enabled:
                    print(
                        f"[CliModelBackend] {self._cli_tool} 실패, "
                        f"{fallback}로 폴백: {err}"
                    )
                    text, err2 = await self._arun_cli(
                        fallback, prompt, self._get_timeout(fallback)
                    )
                    if err2 is not None:
                        raise RuntimeError(
                            f"CLI 백엔드 모두 실패: "
                            f"{self._cli_tool}={err}, {fallback}={err2}"
                        )
                else:
                    raise RuntimeError(
                        f"CLI 백엔드 실패 ({self._cli_tool}): {err}"
                    )

        return self._parse_response(text, tools)

    async def _arun_cli(
        self, tool: str, prompt: str, timeout: float
    ) -> tuple:
        """단일 CLI 도구를 비동기 실행합니다.

        Returns:
            (stdout_text, error_or_None)
        """
        cmd = self._build_cli_command(tool)
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=prompt.encode("utf-8")),
                timeout=timeout,
            )
            if proc.returncode != 0:
                err_text = stderr.decode("utf-8", errors="replace")[:500]
                return "", f"exit {proc.returncode}: {err_text}"
            return stdout.decode("utf-8", errors="replace"), None
        except asyncio.TimeoutError:
            try:
                proc.kill()  # type: ignore[union-attr]
                await asyncio.wait_for(proc.wait(), timeout=5)
            except Exception:
                pass
            return "", f"timeout after {timeout}s"
        except FileNotFoundError:
            return "", f"{tool} binary not found"
        except Exception as exc:
            return "", str(exc)

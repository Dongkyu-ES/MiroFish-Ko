"""
LLM 클라이언트 래퍼
OpenAI 호환 형식으로 통일해 호출합니다.
"""

import json
import os
from typing import Optional, Dict, Any, List

from ..config import Config
from .codex_broker import CodexBroker


class LLMClient:
    """LLM 클라이언트"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        codex_broker: Optional[CodexBroker] = None,
    ):
        self.provider = provider or Config.LLM_PROVIDER
        self.api_key = api_key or Config.LLM_API_KEY
        self.base_url = base_url or Config.LLM_BASE_URL
        self.model = model or Config.LLM_MODEL_NAME
        self.client = None

        # codex_broker가 명시적으로 전달된 경우 Gemini 패스를 건너뜁니다.
        _explicit_broker = codex_broker is not None
        self.codex_broker = codex_broker or CodexBroker()

        # Gemini 빠른 경로 초기화 (명시적 broker가 없을 때만 활성화)
        self.fast_backend = "" if _explicit_broker else os.environ.get("LLM_FAST_BACKEND", "").lower()
        if self.fast_backend == "gemini":
            import openai
            gemini_key = os.environ.get("GEMINI_API_KEY", "")
            gemini_model = os.environ.get("OASIS_GEMINI_MODEL", "gemini-2.0-flash")
            if gemini_key:
                self._gemini_client = openai.OpenAI(
                    api_key=gemini_key,
                    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                )
                self._gemini_model = gemini_model

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: Optional[Dict] = None
    ) -> str:
        """
        채팅 요청을 전송합니다.

        Args:
            messages: 메시지 목록
            temperature: 온도 파라미터
            max_tokens: 최대 토큰 수
            response_format: 응답 형식(예: JSON 모드)

        Returns:
            모델 응답 텍스트
        """
        if self.fast_backend == "gemini" and hasattr(self, "_gemini_client"):
            kwargs: Dict[str, Any] = dict(
                model=self._gemini_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            if response_format and response_format.get("type") == "json_object":
                kwargs["response_format"] = {"type": "json_object"}
            resp = self._gemini_client.chat.completions.create(**kwargs)
            return resp.choices[0].message.content

        if response_format and response_format.get("type") == "json_object":
            json_result = self.codex_broker.chat_json(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return json.dumps(json_result, ensure_ascii=False)
        return self.codex_broker.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def chat_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096
    ) -> Dict[str, Any]:
        """
        채팅 요청을 전송하고 JSON으로 반환합니다.

        Args:
            messages: 메시지 목록
            temperature: 온도 파라미터
            max_tokens: 최대 토큰 수

        Returns:
            파싱된 JSON 객체
        """
        if self.fast_backend == "gemini" and hasattr(self, "_gemini_client"):
            resp = self._gemini_client.chat.completions.create(
                model=self._gemini_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
            content = resp.choices[0].message.content
            return json.loads(content)

        return self.codex_broker.chat_json(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def close(self):
        """Gemini OpenAI 클라이언트의 httpx 연결 풀을 해제한다."""
        if hasattr(self, "_gemini_client") and self._gemini_client is not None:
            try:
                self._gemini_client.close()
            except Exception:
                pass
            self._gemini_client = None

    def __del__(self):
        self.close()

"""
LLM 클라이언트 래퍼
OpenAI 호환 형식으로 통일해 호출합니다.
"""

import json
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
        self.codex_broker = codex_broker
        self.client = None
        self.codex_broker = self.codex_broker or CodexBroker()
    
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
        return self.codex_broker.chat_json(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

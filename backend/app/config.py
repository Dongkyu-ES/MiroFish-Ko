"""
설정 관리
프로젝트 루트의 `.env` 파일에서 설정을 통합 로드합니다.
"""

import os
import shutil
from dotenv import load_dotenv

# 프로젝트 루트의 `.env` 파일 로드
# 경로: MiroFish/.env (backend/app/config.py 기준 상대 경로)
project_root_env = os.path.join(os.path.dirname(__file__), '../../.env')

if os.path.exists(project_root_env):
    load_dotenv(project_root_env, override=True)
else:
    # 루트에 `.env`가 없으면 시스템 환경 변수를 사용(운영 환경용)
    load_dotenv(override=True)


class Config:
    """Flask 설정 클래스"""
    
    # Flask 설정
    SECRET_KEY = os.environ.get('SECRET_KEY', 'mirofish-secret-key')
    DEBUG = os.environ.get('FLASK_DEBUG', 'True').lower() == 'true'
    
    # JSON 설정 - ASCII 이스케이프 비활성화(문자가 `\\uXXXX` 대신 그대로 표시)
    JSON_AS_ASCII = False
    
    # LLM 설정 (Codex CLI 고정)
    LLM_PROVIDER = os.environ.get('LLM_PROVIDER', 'codex_cli')
    LLM_API_KEY = os.environ.get('LLM_API_KEY')
    LLM_BASE_URL = os.environ.get('LLM_BASE_URL', '')
    LLM_MODEL_NAME = os.environ.get('LLM_MODEL_NAME', 'gpt-5.4')
    
    # Codex CLI 설정
    CODEX_BIN = os.environ.get('CODEX_BIN', 'codex')
    CODEX_JSON_MODEL = os.environ.get('CODEX_JSON_MODEL', 'gpt-5.3-codex-spark')
    CODEX_REASONING_MODEL = os.environ.get('CODEX_REASONING_MODEL', 'gpt-5.4')
    CODEX_JSON_REASONING_EFFORT = os.environ.get('CODEX_JSON_REASONING_EFFORT', 'high')
    CODEX_REASONING_EFFORT = os.environ.get('CODEX_REASONING_EFFORT', 'high')
    CODEX_SERVICE_TIER = os.environ.get('CODEX_SERVICE_TIER', 'fast')
    CODEX_SANDBOX = os.environ.get('CODEX_SANDBOX', 'read-only')
    CODEX_TIMEOUT_JSON_SEC = int(os.environ.get('CODEX_TIMEOUT_JSON_SEC', '120'))
    CODEX_TIMEOUT_REASONING_SEC = int(os.environ.get('CODEX_TIMEOUT_REASONING_SEC', '600'))
    CODEX_TASKS_DIR = os.environ.get(
        'CODEX_TASKS_DIR',
        os.path.join(os.path.dirname(__file__), '../uploads/codex_tasks')
    )
    
    # Claude CLI 폴백 설정 (Codex CLI 레이트리밋 시 2차 폴백)
    CLAUDE_FALLBACK_ENABLED = os.environ.get('CLAUDE_FALLBACK_ENABLED', 'false').lower() == 'true'
    CLAUDE_PRIMARY = os.environ.get('CLAUDE_PRIMARY', 'false').lower() == 'true'
    CLAUDE_BIN = os.environ.get('CLAUDE_BIN', 'claude')
    CLAUDE_MODEL_REASONING = os.environ.get('CLAUDE_MODEL_REASONING', 'claude-opus-4-6')
    CLAUDE_MODEL_FAST = os.environ.get('CLAUDE_MODEL_FAST', 'claude-haiku-4-5')
    CLAUDE_TIMEOUT_SEC = int(os.environ.get('CLAUDE_TIMEOUT_SEC', '120'))

    # OASIS 시뮬레이션 모델 폴백 설정 (camel-ai 직접 호출)
    OASIS_FALLBACK_ENABLED = os.environ.get('OASIS_FALLBACK_ENABLED', 'true').lower() == 'true'
    OASIS_FALLBACK_MODEL = os.environ.get('OASIS_FALLBACK_MODEL', 'claude-haiku-4-5')

    # Zep 설정
    ZEP_API_KEY = os.environ.get('ZEP_API_KEY')
    
    # 그래프 백엔드 설정
    GRAPH_BACKEND = os.environ.get('GRAPH_BACKEND', 'zep')
    LOCAL_GRAPH_DB_PATH = os.environ.get(
        'LOCAL_GRAPH_DB_PATH',
        os.path.join(os.path.dirname(__file__), '../uploads/local_graphs.sqlite3')
    )
    
    # 파일 업로드 설정
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), '../uploads')
    ALLOWED_EXTENSIONS = {'pdf', 'md', 'txt', 'markdown'}
    
    # 텍스트 처리 설정
    DEFAULT_CHUNK_SIZE = 500  # 기본 청크 크기
    DEFAULT_CHUNK_OVERLAP = 50  # 기본 청크 겹침 크기
    
    # OASIS 시뮬레이션 설정
    OASIS_DEFAULT_MAX_ROUNDS = int(os.environ.get('OASIS_DEFAULT_MAX_ROUNDS', '10'))
    OASIS_SIMULATION_DATA_DIR = os.path.join(os.path.dirname(__file__), '../uploads/simulations')
    
    # OASIS 플랫폼별 사용 가능 액션
    OASIS_TWITTER_ACTIONS = [
        'CREATE_POST', 'LIKE_POST', 'REPOST', 'FOLLOW', 'DO_NOTHING', 'QUOTE_POST'
    ]
    OASIS_REDDIT_ACTIONS = [
        'LIKE_POST', 'DISLIKE_POST', 'CREATE_POST', 'CREATE_COMMENT',
        'LIKE_COMMENT', 'DISLIKE_COMMENT', 'SEARCH_POSTS', 'SEARCH_USER',
        'TREND', 'REFRESH', 'DO_NOTHING', 'FOLLOW', 'MUTE'
    ]
    
    # Report Agent 설정
    REPORT_AGENT_MAX_TOOL_CALLS = int(os.environ.get('REPORT_AGENT_MAX_TOOL_CALLS', '5'))
    REPORT_AGENT_MAX_REFLECTION_ROUNDS = int(os.environ.get('REPORT_AGENT_MAX_REFLECTION_ROUNDS', '2'))
    REPORT_AGENT_TEMPERATURE = float(os.environ.get('REPORT_AGENT_TEMPERATURE', '0.5'))
    
    @classmethod
    def uses_codex_cli(cls) -> bool:
        return True

    @classmethod
    def uses_local_graph(cls) -> bool:
        return cls.GRAPH_BACKEND == 'local_sqlite'
    
    @classmethod
    def validate(cls):
        """필수 설정 검증"""
        errors = []
        if not shutil.which(cls.CODEX_BIN):
            errors.append(f"CODEX_BIN 실행 파일을 찾을 수 없습니다: {cls.CODEX_BIN}")
        if not cls.uses_local_graph() and not cls.ZEP_API_KEY:
            errors.append("ZEP_API_KEY가 설정되지 않았습니다.")
        return errors

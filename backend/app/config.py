"""
설정 관리
프로젝트 루트의 `.env` 파일에서 설정을 통합 로드합니다.
"""

import os
from dotenv import load_dotenv

# 프로젝트 루트의 `.env` 파일 로드
# 경로: MiroFish/.env (backend/app/config.py 기준 상대 경로)
project_root_env = os.path.join(os.path.dirname(__file__), '../../.env')

if os.path.exists(project_root_env):
    load_dotenv(project_root_env, override=False)
else:
    # 루트에 `.env`가 없으면 시스템 환경 변수를 사용(운영 환경용)
    load_dotenv(override=False)


class Config:
    """Flask 설정 클래스"""
    
    # Flask 설정
    SECRET_KEY = os.environ.get('SECRET_KEY', '')
    DEBUG = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    
    # JSON 설정 - ASCII 이스케이프 비활성화(문자가 `\\uXXXX` 대신 그대로 표시)
    JSON_AS_ASCII = False
    
    # LLM 설정(OpenAI 형식으로 통일)
    LLM_API_KEY = os.environ.get('LLM_API_KEY')
    LLM_BASE_URL = os.environ.get('LLM_BASE_URL', 'https://api.openai.com/v1')
    LLM_MODEL_NAME = os.environ.get('LLM_MODEL_NAME', 'gpt-4o-mini')
    
    # Zep 설정
    ZEP_API_KEY = os.environ.get('ZEP_API_KEY')

    # Graph backend runtime mode
    GRAPH_BACKEND = os.environ.get('GRAPH_BACKEND', 'zep')
    ENGINE_BASE_URL = os.environ.get('ENGINE_BASE_URL', 'http://127.0.0.1:8123')
    ENGINE_TIMEOUT_SECONDS = int(os.environ.get('ENGINE_TIMEOUT_SECONDS', '30'))
    ENGINE_SHADOW_EVAL_ENABLED = os.environ.get('ENGINE_SHADOW_EVAL_ENABLED', 'false').lower() == 'true'
    ENGINE_DEFAULT_PORT = int(os.environ.get('ENGINE_PORT', '8123'))
    
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
    def requires_zep_api_key(cls) -> bool:
        return cls.GRAPH_BACKEND in {'zep', 'shadow_eval'}
    
    @classmethod
    def validate(cls):
        """필수 설정 검증"""
        errors = []
        if cls.GRAPH_BACKEND not in {'zep', 'shadow_eval', 'local_primary'}:
            errors.append("GRAPH_BACKEND는 zep, shadow_eval, local_primary 중 하나여야 합니다.")
        if not cls.SECRET_KEY:
            errors.append("SECRET_KEY가 설정되지 않았습니다.")
        if not cls.LLM_API_KEY:
            errors.append("LLM_API_KEY가 설정되지 않았습니다.")
        if cls.requires_zep_api_key() and not cls.ZEP_API_KEY:
            errors.append("ZEP_API_KEY가 설정되지 않았습니다.")
        return errors

"""
MiroFish Backend 실행 진입점
"""

import os
import sys

# Windows 콘솔 한글/중문 깨짐 방지: 모든 import 이전에 UTF-8 설정
if sys.platform == 'win32':
    # Python이 UTF-8을 사용하도록 환경 변수 설정
    os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
    # 표준 출력 스트림을 UTF-8로 재설정
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# 프로젝트 루트 경로 추가
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from backend.bootstrap_graph_backend import bootstrap_graph_backend

bootstrap_graph_backend()

from backend.app import create_app
from backend.app.config import Config
from backend.app.parity_engine.runtime_checks import EngineUnavailableError, ensure_engine_ready


def main():
    """메인 함수"""
    # 설정 검증
    errors = Config.validate()
    if errors:
        print("설정 오류:")
        for err in errors:
            print(f"  - {err}")
        print("\n.env 파일 설정을 확인해 주세요.")
        sys.exit(1)

    if Config.GRAPH_BACKEND == "local_primary":
        try:
            ensure_engine_ready(timeout_seconds=Config.ENGINE_TIMEOUT_SECONDS)
        except EngineUnavailableError as exc:
            print(f"Parity engine startup check failed: {exc}")
            sys.exit(1)
    
    # 앱 생성
    app = create_app()
    
    # 실행 설정 조회
    host = os.environ.get('FLASK_HOST', '0.0.0.0')
    port = int(os.environ.get('FLASK_PORT', 5001))
    debug = Config.DEBUG
    
    # 서버 시작
    app.run(host=host, port=port, debug=debug, threaded=True)


if __name__ == '__main__':
    main()

from __future__ import annotations

import os
import threading
import time
from contextlib import contextmanager
from socket import socket

from werkzeug.serving import make_server

from backend.app.parity_engine.server import create_engine_app


def _pick_free_port() -> int:
    with socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@contextmanager
def running_engine_server(tmp_path):
    port = _pick_free_port()
    base_url = f"http://127.0.0.1:{port}"
    env_updates = {
        "ENGINE_HOST": "127.0.0.1",
        "ENGINE_PORT": str(port),
        "ENGINE_BASE_URL": base_url,
        "GRAPHITI_DB_PATH": str(tmp_path / "graphiti.kuzu"),
        "GRAPHITI_PARITY_ARTIFACT_DIR": str(tmp_path / "artifacts"),
        "GRAPHITI_EPISODE_INLINE": "true",
    }
    previous_env = {key: os.environ.get(key) for key in env_updates}
    for key, value in env_updates.items():
        os.environ[key] = value
    (tmp_path / "artifacts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "artifacts" / "cutover_status.json").write_text(
        '{"verdict":"eligible_for_local_primary","hard_gates_passed":true}',
        encoding="utf-8",
    )

    app, _ = create_engine_app(testing=True)
    os.environ["ENGINE_BASE_URL"] = base_url
    server = make_server("127.0.0.1", port, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.1)
    try:
        yield base_url
    finally:
        server.shutdown()
        thread.join(timeout=2)
        for key, value in previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

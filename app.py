"""Root entrypoint for the standalone Graphiti-backed parity engine."""

from __future__ import annotations

from backend.app.parity_engine.server import create_engine_app


def main() -> None:
    app, config = create_engine_app()
    app.run(
        host=str(config["HOST"]),
        port=int(config["PORT"]),
        debug=False,
        threaded=True,
    )


if __name__ == "__main__":
    main()

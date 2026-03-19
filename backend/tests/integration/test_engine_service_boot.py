import importlib

from backend.app.parity_engine.server import create_engine_app


def test_engine_service_defaults_to_port_8123():
    app, config = create_engine_app(testing=True)

    assert app.config["TESTING"] is True
    assert config["PORT"] == 8123
    assert config["GRAPHITI_BACKEND"] == "kuzu"


def test_engine_settings_load_root_dotenv(monkeypatch, tmp_path):
    config_module = importlib.import_module("backend.app.parity_engine.config")
    env_path = tmp_path / ".env"
    env_path.write_text("ENGINE_PORT=9234\nGRAPHITI_DB_PATH=./tmp/from-dotenv.kuzu\n", encoding="utf-8")

    monkeypatch.setattr(config_module, "ENGINE_ENV_PATH", env_path)
    monkeypatch.delenv("ENGINE_PORT", raising=False)
    monkeypatch.delenv("GRAPHITI_DB_PATH", raising=False)

    config_module.load_engine_dotenv(force_reload=True)
    settings = config_module.load_engine_settings()

    assert settings.port == 9234
    assert settings.graphiti_db_path == "./tmp/from-dotenv.kuzu"

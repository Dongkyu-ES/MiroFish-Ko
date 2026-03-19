from backend.app.parity_engine.logging_config import configure_logging


def test_engine_logging_writes_to_stdout(capsys):
    logger = configure_logging(
        logger_name="mirofish.parity.test",
        level="INFO",
        stdout_logging=True,
    )

    logger.info("engine boot")
    captured = capsys.readouterr()

    assert "engine boot" in captured.out

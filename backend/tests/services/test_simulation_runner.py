from backend.app.services.simulation_runner import SimulationRunner


def test_resolve_python_executable_prefers_env_override(monkeypatch):
    monkeypatch.setenv("SIMULATION_PYTHON_EXECUTABLE", "/custom/python")

    monkeypatch.setattr(
        SimulationRunner,
        "_candidate_python_executables",
        classmethod(lambda cls: ["/custom/python", "/fallback/python"]),
    )
    monkeypatch.setattr(
        SimulationRunner,
        "_python_supports_runtime_dependencies",
        classmethod(lambda cls, path: path == "/custom/python"),
    )

    assert SimulationRunner._resolve_python_executable() == "/custom/python"


def test_resolve_python_executable_falls_back_when_current_python_is_unhealthy(monkeypatch):
    monkeypatch.delenv("SIMULATION_PYTHON_EXECUTABLE", raising=False)
    monkeypatch.setattr("backend.app.services.simulation_runner.sys.executable", "/bad/python")

    monkeypatch.setattr(
        SimulationRunner,
        "_candidate_python_executables",
        classmethod(lambda cls: ["/bad/python", "/good/python"]),
    )
    monkeypatch.setattr(
        SimulationRunner,
        "_python_supports_runtime_dependencies",
        classmethod(lambda cls, path: path == "/good/python"),
    )

    assert SimulationRunner._resolve_python_executable() == "/good/python"


def test_start_simulation_fails_fast_when_child_process_exits_immediately(tmp_path, monkeypatch):
    sim_id = "sim_fastfail"
    sim_dir = tmp_path / sim_id
    sim_dir.mkdir(parents=True)
    (sim_dir / "simulation_config.json").write_text(
        '{"time_config": {"total_simulation_hours": 1, "minutes_per_round": 60}}',
        encoding="utf-8",
    )
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "run_parallel_simulation.py").write_text("print('boom')", encoding="utf-8")

    class FakeProcess:
        pid = 12345
        returncode = 1

        def poll(self):
            return 1

    def fake_popen(*args, **kwargs):
        stdout = kwargs["stdout"]
        stdout.write("오류: 누락 No module named 'camel'\\n")
        stdout.flush()
        return FakeProcess()

    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(SimulationRunner, "SCRIPTS_DIR", str(scripts_dir))
    monkeypatch.setattr(SimulationRunner, "_resolve_python_executable", classmethod(lambda cls: "/good/python"))
    monkeypatch.setattr("backend.app.services.simulation_runner.subprocess.Popen", fake_popen)
    monkeypatch.setattr("backend.app.services.simulation_runner.time.sleep", lambda _: None)
    monkeypatch.setattr(SimulationRunner, "_run_states", {})
    monkeypatch.setattr(SimulationRunner, "_processes", {})
    monkeypatch.setattr(SimulationRunner, "_action_queues", {})
    monkeypatch.setattr(SimulationRunner, "_monitor_threads", {})
    monkeypatch.setattr(SimulationRunner, "_stdout_files", {})
    monkeypatch.setattr(SimulationRunner, "_stderr_files", {})
    monkeypatch.setattr(SimulationRunner, "_graph_memory_enabled", {})

    try:
        SimulationRunner.start_simulation(sim_id, platform="parallel")
    except RuntimeError as exc:
        state = SimulationRunner.get_run_state(sim_id)
        assert "camel" in str(exc)
        assert state is not None
        assert state.runner_status.value == "failed"
        assert "camel" in (state.error or "")
        assert sim_id not in SimulationRunner._processes
    else:
        raise AssertionError("expected immediate child-exit to fail fast")

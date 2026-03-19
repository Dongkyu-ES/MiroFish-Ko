from backend.app import create_app
from backend.app.services.simulation_manager import SimulationState, SimulationStatus
from backend.app.services.simulation_runner import SimulationRuntimeUnavailableError


def test_simulation_start_returns_structured_runtime_error(monkeypatch):
    class FakeManager:
        def get_simulation(self, simulation_id):
            return SimulationState(
                simulation_id=simulation_id,
                project_id="proj_test",
                graph_id="graph_test",
                status=SimulationStatus.READY,
            )

        def _save_simulation_state(self, state):
            self.saved_state = state

    fake_manager = FakeManager()

    monkeypatch.setattr("backend.app.api.simulation.SimulationManager", lambda: fake_manager)
    monkeypatch.setattr(
        "backend.app.api.simulation.SimulationRunner.start_simulation",
        lambda **kwargs: (_ for _ in ()).throw(
            SimulationRuntimeUnavailableError(
                "필수 런타임 모듈(sqlite3, camel, oasis)을 import할 수 있는 Python 인터프리터를 찾지 못했습니다"
            )
        ),
    )

    app = create_app()
    client = app.test_client()

    response = client.post(
        "/api/simulation/start",
        json={
            "simulation_id": "sim_test",
            "platform": "parallel",
            "enable_graph_memory_update": False,
        },
    )

    payload = response.get_json()

    assert response.status_code == 503
    assert payload["success"] is False
    assert payload["error_code"] == "simulation_runtime_unavailable"
    assert "camel" in payload["error"]

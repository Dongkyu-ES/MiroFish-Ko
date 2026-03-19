from backend.app.parity_engine.server import create_engine_app


def test_engine_service_exposes_health_and_ready_endpoints():
    app, _ = create_engine_app(testing=True)
    client = app.test_client()

    health_response = client.get("/health")
    ready_response = client.get("/ready")

    assert health_response.status_code == 200
    assert ready_response.status_code == 200
    assert health_response.get_json()["status"] == "ok"
    assert ready_response.get_json()["status"] == "ready"

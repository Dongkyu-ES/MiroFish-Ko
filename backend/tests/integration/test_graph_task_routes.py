from backend.app import create_app
from backend.app.models.task import TaskManager


def test_graph_tasks_route_returns_task_dicts_without_500():
    app = create_app()
    client = app.test_client()
    task_manager = TaskManager()
    task_id = task_manager.create_task("graph_build")

    response = client.get("/api/graph/tasks")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["success"] is True
    assert any(item["task_id"] == task_id for item in payload["data"])

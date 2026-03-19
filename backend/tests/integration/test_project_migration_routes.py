import json

from backend.app import create_app
from backend.app.models.project import ProjectManager, ProjectStatus


def test_project_migration_routes_use_runtime_service(monkeypatch, tmp_path):
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(tmp_path / "projects"))
    project = ProjectManager.create_project("Migration API")
    project.graph_id = "legacy_graph_01"
    project.status = ProjectStatus.GRAPH_COMPLETED
    project.ontology = {"entity_types": [], "edge_types": []}
    ProjectManager.save_project(project)
    ProjectManager.save_extracted_text(project.project_id, "Alice works for Example Labs.")

    class FakeService:
        def migrate_project(self, project_id):
            saved = ProjectManager.get_project(project_id)
            saved.migration_status = "completed"
            saved.local_primary_eligible = True
            ProjectManager.save_project(saved)
            return {
                "project_id": project_id,
                "graph_id": "legacy_graph_01",
                "migration_status": "completed",
            }

        def get_migration_status(self, project_id):
            return {
                "project_id": project_id,
                "graph_id": "legacy_graph_01",
                "migration_status": "completed",
                "local_primary_eligible": True,
            }

    import backend.app.api.graph as graph_api

    monkeypatch.setattr(graph_api, "build_project_migration_service", lambda: FakeService())

    app = create_app()
    client = app.test_client()

    migrate_response = client.post(f"/api/graph/project/{project.project_id}/migrate-local-primary")
    status_response = client.get(f"/api/graph/project/{project.project_id}/migration-status")

    assert migrate_response.status_code == 200
    assert status_response.status_code == 200
    assert migrate_response.get_json()["data"]["migration_status"] == "completed"
    assert status_response.get_json()["data"]["local_primary_eligible"] is True

from backend.app.models.project import Project, ProjectManager, ProjectStatus
from backend.app.parity_engine.migration import ProjectMigrationService


def test_project_migration_preserves_graph_id_and_marks_completed(tmp_path, monkeypatch):
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(tmp_path / "projects"))
    project = ProjectManager.create_project("Migration Test")
    project.graph_id = "legacy_graph_01"
    project.status = ProjectStatus.GRAPH_COMPLETED
    ProjectManager.save_project(project)

    class Importer:
        def import_project_graph(self, project_id, graph_id):
            return {"project_id": project_id, "graph_id": graph_id}

        def rollback_project_graph(self, project_id, graph_id):
            raise AssertionError("rollback should not be called")

    class Verifier:
        def verify_project_graph(self, project_id, graph_id):
            return {"passed": True}

    service = ProjectMigrationService(importer=Importer(), verifier=Verifier())
    result = service.migrate_project(project.project_id)
    saved = ProjectManager.get_project(project.project_id)

    assert result["graph_id"] == "legacy_graph_01"
    assert result["migration_status"] == "completed"
    assert saved is not None
    assert saved.graph_id == "legacy_graph_01"


def test_project_migration_rolls_back_on_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(tmp_path / "projects"))
    project = ProjectManager.create_project("Migration Rollback")
    project.graph_id = "legacy_graph_99"
    project.status = ProjectStatus.GRAPH_COMPLETED
    ProjectManager.save_project(project)

    rollback_calls = []

    class Importer:
        def import_project_graph(self, project_id, graph_id):
            raise RuntimeError("boom")

        def rollback_project_graph(self, project_id, graph_id):
            rollback_calls.append((project_id, graph_id))

    class Verifier:
        def verify_project_graph(self, project_id, graph_id):
            return {"passed": True}

    service = ProjectMigrationService(importer=Importer(), verifier=Verifier())

    try:
        service.migrate_project(project.project_id)
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected migration failure")

    saved = ProjectManager.get_project(project.project_id)
    assert rollback_calls == [(project.project_id, "legacy_graph_99")]
    assert saved is not None
    assert saved.graph_id == "legacy_graph_99"

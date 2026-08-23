from app.domain.states.task_state import TaskStatus
from app.services.task_service import TaskService
from app.storage.orm import AuditEventRecord
from tests.project_test_support import create_project_task, project_workspace


def test_create_and_read_task(db_session):
    service = TaskService(db_session)
    created = create_project_task(db_session,
        title="Release verification",
        goal="Check release readiness",
    )

    loaded = service.get_task(created.id)

    assert loaded is not None
    assert loaded.id == created.id
    assert loaded.status == TaskStatus.CREATED
    assert loaded.workspace == project_workspace(db_session)


def test_state_transition_creates_audit_event(db_session):
    service = TaskService(db_session)
    created = create_project_task(db_session,
        title="Workflow test",
        goal="Exercise state transition",
    )

    service.transition_task(created.id, TaskStatus.PLANNING)
    loaded = service.get_task(created.id)

    assert loaded is not None
    assert loaded.status == TaskStatus.PLANNING
    events = db_session.query(AuditEventRecord).filter_by(task_id=created.id).all()
    assert any(event.event_type == "TASK_STATE_CHANGED" for event in events)

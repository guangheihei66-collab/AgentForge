"""Persistence boundary for immutable generated plan versions."""

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..storage.orm import PlanRecord


class PlanRepository:
    def __init__(self, session: Session):
        self.session = session

    def next_version(self, task_id: str) -> int:
        current = self.session.query(func.max(PlanRecord.version)).filter_by(task_id=task_id).scalar()
        return int(current or 0) + 1

    def highest_for_task(self, task_id: str) -> PlanRecord | None:
        return (
            self.session.query(PlanRecord)
            .filter_by(task_id=task_id)
            .order_by(PlanRecord.version.desc(), PlanRecord.created_at.desc())
            .first()
        )

    def count_replans(self, task_id: str) -> int:
        plans = self.session.query(PlanRecord).filter_by(task_id=task_id).all()
        return sum(
            isinstance(plan.plan_json.get("replan_lineage"), dict) for plan in plans
        )

    def create(self, *, task_id: str, version: int, plan_json: dict, validation_status: str) -> PlanRecord:
        plan = PlanRecord(
            task_id=task_id,
            version=version,
            plan_json=plan_json,
            validation_status=validation_status,
        )
        self.session.add(plan)
        self.session.flush()
        return plan

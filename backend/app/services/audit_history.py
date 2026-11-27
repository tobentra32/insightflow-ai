from dataclasses import dataclass
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.user import User


@dataclass(frozen=True)
class AuditHistoryPage:
    """A page of audit entries and the total number of matching entries."""

    items: list[dict[str, Any]]
    total: int


def get_audit_history(
    db: Session,
    *,
    entity_type: str,
    entity_id: int,
    skip: int,
    limit: int,
    legacy_conditions: tuple[Any, ...] | None = None,
) -> AuditHistoryPage:
    """Retrieve a paginated audit history for any entity.

    New entries are located by their generic entity_type/entity_id fields.
    Optional legacy conditions allow an entity route to include older rows
    created before those generic fields existed. Legacy rows are included
    only when both generic identity fields are NULL.

    This service deliberately does not perform authorization. The calling
    route must enforce entity-specific access rules before calling it.
    """

    current_entity_condition = and_(
        AuditLog.entity_type == entity_type,
        AuditLog.entity_id == entity_id,
    )

    if legacy_conditions:
        legacy_entity_condition = and_(
            AuditLog.entity_type.is_(None),
            AuditLog.entity_id.is_(None),
            *legacy_conditions,
        )
        history_condition = or_(
            current_entity_condition,
            legacy_entity_condition,
        )
    else:
        history_condition = current_entity_condition

    total = db.scalar(
        select(func.count(AuditLog.id)).where(history_condition)
    ) or 0

    rows = db.execute(
        select(AuditLog, User.name)
        .outerjoin(User, AuditLog.user_id == User.id)
        .where(history_condition)
        .order_by(
            AuditLog.changed_at.desc(),
            AuditLog.id.desc(),
        )
        .offset(skip)
        .limit(limit)
    ).all()

    items = [
        {
            "id": log.id,
            "user_id": log.user_id,
            "changed_by_name": user_name,
            "action": log.action,
            "entity_type": log.entity_type,
            "entity_id": log.entity_id,
            "field_name": log.field_name,
            "old_value": log.old_value,
            "new_value": log.new_value,
            "changed_at": log.changed_at,
        }
        for log, user_name in rows
    ]

    return AuditHistoryPage(items=items, total=total)

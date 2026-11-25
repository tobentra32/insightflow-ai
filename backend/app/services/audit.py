
from typing import Any

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


def record_audit_changes(
    db: Session,
    *,
    user_id: int,
    entity_type: str,
    entity_id: int,
    action: str,
    changes: dict[str, tuple[Any | None, Any | None]],
) -> None:
    """
    Add one audit-log row for each supplied field change.

    Does not commit. The calling operation controls the transaction.
    """

    if not entity_type or len(entity_type) > 50:
        raise ValueError("Invalid audit entity type.")

    if not action or len(action) > 50:
        raise ValueError("Invalid audit action.")

    if entity_id <= 0:
        raise ValueError("Invalid audit entity ID.")

    for field_name, (old_value, new_value) in changes.items():
        if not field_name or len(field_name) > 255:
            raise ValueError("Invalid audit field name.")

        if old_value == new_value:
            continue

        db.add(
            AuditLog(
                user_id=user_id,
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                field_name=field_name,
                old_value=old_value,
                new_value=new_value,
            )
        )

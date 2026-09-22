import json
from typing import Any

from sqlalchemy.orm import Session

from .models import AuditLog


def _json(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)


def audit(
    db: Session,
    *,
    entity_type: str,
    entity_id: str | int | None,
    action: str,
    before: Any = None,
    after: Any = None,
    reason: str | None = None,
    actor: str = "api",
) -> None:
    db.add(
        AuditLog(
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            action=action,
            before_json=_json(before),
            after_json=_json(after),
            reason=reason,
            actor=actor,
        )
    )

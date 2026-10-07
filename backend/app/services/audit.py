from sqlalchemy.orm import Session

from app.db.models import AuditLog


def audit(db: Session, actor: str, action: str, **detail) -> None:
    """Append to the audit log. Never pass secret values in `detail`."""
    db.add(AuditLog(actor=actor, action=action, detail_json=detail or None))

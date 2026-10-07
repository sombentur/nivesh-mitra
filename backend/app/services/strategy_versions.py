from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import StrategyVersion
from app.rules import rules_hash


def get_or_create(db: Session, engine: str, rules: dict) -> StrategyVersion:
    """Return the stored snapshot of these exact rules, creating it the first time they're used."""
    h = rules_hash(rules)
    row = db.scalar(select(StrategyVersion).where(StrategyVersion.config_hash == h))
    if row is None:
        row = StrategyVersion(engine=engine, version=rules["version"], config_hash=h, config_json=rules)
        db.add(row)
        db.flush()
    return row

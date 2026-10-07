"""Run database migrations at start-up, backing up the database first."""

import shutil
from datetime import datetime
from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

from app.config import get_config
from app.db.base import engine

BACKEND_DIR = Path(__file__).resolve().parents[2]
KEEP_BACKUPS = 7  # the database grows to ~150 MB once fund history is downloaded


def _alembic_config() -> AlembicConfig:
    cfg = AlembicConfig(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.attributes["configure_logger"] = False  # keep uvicorn's logging intact
    return cfg


def backup_database(reason: str) -> Path | None:
    config = get_config()
    if not config.db_path.exists():
        return None
    backup_dir = config.data_dir / "backups"
    backup_dir.mkdir(exist_ok=True)
    target = backup_dir / f"niveshmitra-{datetime.now():%Y%m%d-%H%M%S}-{reason}.db"
    if reason == "pre-migration":
        shutil.copy2(config.db_path, target)  # nothing else is writing yet
    else:
        with engine.connect() as conn:  # consistent, compacted copy while the app keeps running
            conn.exec_driver_sql(f"VACUUM INTO '{target.as_posix()}'")
    for old in sorted(backup_dir.glob("niveshmitra-*.db"), key=lambda p: p.stat().st_mtime)[:-KEEP_BACKUPS]:
        old.unlink()
    return target


def upgrade_to_head() -> None:
    cfg = _alembic_config()
    head = ScriptDirectory.from_config(cfg).get_current_head()
    with engine.connect() as conn:
        current = MigrationContext.configure(conn).get_current_revision()
    if current != head:
        backup_database("pre-migration")
        command.upgrade(cfg, "head")

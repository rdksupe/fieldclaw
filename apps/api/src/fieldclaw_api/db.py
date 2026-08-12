from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from fieldclaw_api.config import settings

settings.fieldclaw_db_path.parent.mkdir(parents=True, exist_ok=True)
settings.fieldclaw_proofs_dir.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    f"sqlite:///{settings.fieldclaw_db_path}",
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _sqlite_pragma(dbapi_conn, _):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from fieldclaw_api import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate_sqlite_columns()


def _migrate_sqlite_columns() -> None:
    """Add columns introduced after first create_all (SQLite has no ALTER auto)."""
    wanted = {
        "projects": {
            "inbox_email": "VARCHAR",
            "kb_relpath": "VARCHAR",
        }
    }
    with engine.begin() as conn:
        for table, cols in wanted.items():
            existing = {
                row[1]
                for row in conn.exec_driver_sql(
                    f"PRAGMA table_info({table})"
                ).fetchall()
            }
            for col, typ in cols.items():
                if col not in existing:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")

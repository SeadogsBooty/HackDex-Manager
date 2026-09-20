from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from platform_paths import (
    data_path,
    running_as_desktop,
)


DATABASE_URL = f"sqlite:///{data_path('hackdex-manager.db')}"

engine = create_engine(
    DATABASE_URL,
    connect_args={
        "check_same_thread": False,
        "timeout": 30,
    },
)


@event.listens_for(
    engine,
    "connect",
)
def configure_sqlite_connection(
    dbapi_connection,
    connection_record,
):
    """
    Keep short concurrent HackDex operations from failing merely
    because another thread is finishing a SQLite write.

    WAL is enabled only for the native desktop edition because its
    database lives in the user's local application-data directory.
    Docker deployments retain their existing journal mode.
    """
    cursor = dbapi_connection.cursor()

    try:
        cursor.execute(
            "PRAGMA busy_timeout=30000"
        )

        cursor.execute(
            "PRAGMA foreign_keys=ON"
        )

        if running_as_desktop():
            cursor.execute(
                "PRAGMA journal_mode=WAL"
            )

            cursor.execute(
                "PRAGMA synchronous=NORMAL"
            )

    finally:
        cursor.close()


SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()

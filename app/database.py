from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from platform_paths import data_path

DATABASE_URL = f"sqlite:///{data_path('hackdex-manager.db')}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()

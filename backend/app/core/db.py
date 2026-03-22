from sqlmodel import create_engine

from app.core.config import settings


engine = create_engine(
    settings.sqlalchemy_database_uri,
    max_overflow=settings.DB_CONNECTION_POOL_MAX_OVERFLOW,
)

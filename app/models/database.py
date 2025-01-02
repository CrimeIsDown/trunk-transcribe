import os

from sqlmodel import create_engine

SQLALCHEMY_DATABASE_URL = f"postgresql+psycopg://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}@{os.getenv('POSTGRES_HOST')}/{os.getenv('POSTGRES_DB')}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    max_overflow=int(os.getenv("DB_CONNECTION_POOL_MAX_OVERFLOW", 100)),
)

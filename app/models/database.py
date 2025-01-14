import os
from urllib.parse import quote_plus

from sqlmodel import create_engine

SQLALCHEMY_DATABASE_URL = f"postgresql+psycopg://{os.getenv('POSTGRES_USER')}:{quote_plus(os.getenv('POSTGRES_PASSWORD', 'changeme'))}@{os.getenv('POSTGRES_HOST')}/{os.getenv('POSTGRES_DB')}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    max_overflow=int(os.getenv("DB_CONNECTION_POOL_MAX_OVERFLOW", 100)),
    echo=True,
)

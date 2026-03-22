from app.core.config import settings
from app.core.db import engine as core_engine

SQLALCHEMY_DATABASE_URL = settings.sqlalchemy_database_uri
engine = core_engine

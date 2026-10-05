from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


class Settings(BaseSettings):
    database_url: str = (
        "postgresql+psycopg://signalloop:local-development-only@localhost:5433/signalloop"
    )
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_engine():
    return create_engine(Settings().database_url, pool_pre_ping=True)


def get_session():
    factory = sessionmaker(get_engine(), expire_on_commit=False)
    with factory() as session:
        with session.begin():
            yield session

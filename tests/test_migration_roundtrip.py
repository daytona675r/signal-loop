from uuid import uuid4

from alembic.config import Config
from sqlalchemy import inspect, text

from alembic import command


def test_migrations_upgrade_downgrade_upgrade(engine):
    # Separate disposable schema; never downgrade a populated user schema.
    schema = "test_roundtrip_" + uuid4().hex
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        config = Config("alembic.ini")
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        assert "hypothesis_version" in inspect(connection).get_table_names()
        command.downgrade(config, "base")
        assert inspect(connection).get_table_names() == ["alembic_version"]
        command.upgrade(config, "head")
        command.check(config)
        connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))

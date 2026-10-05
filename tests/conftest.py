import os
from uuid import uuid4

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from alembic import command
from signalloop.api.app import app
from signalloop.db.session import get_session


@pytest.fixture(scope="session")
def engine():
    """Only create/drop our random schema, never reset the development database."""
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.fail("Set TEST_DATABASE_URL to a PostgreSQL database with CREATE SCHEMA permission")
    admin = create_engine(url)
    schema = "test_signalloop_" + uuid4().hex
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        config = Config("alembic.ini")
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.fixture
def client(engine):
    def override_session():
        with Session(engine, expire_on_commit=False) as session, session.begin():
            yield session

    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def hypothesis_payload():
    return {
        "title": "Removable Modular Rear Storage System",
        "domain": "Camper / Vanlife / Overlanding",
        "created_by": "mario",
        "version": {
            "target_customer": "Ducato / Jumper / Boxer camper and dual-use owners",
            "problem": "Existing organised storage solutions often require permanent installation.",
            "offer": (
                "Removable modular rear storage system without permanent vehicle modifications."
            ),
            "price_assumption": "449.00",
            "currency": "EUR",
            "success_criteria": "Validate demand and willingness to pay; currently assumptions.",
            "change_reason": "Initial unvalidated assumptions",
            "created_by": "mario",
        },
    }


@pytest.fixture
def hypothesis(client, hypothesis_payload):
    response = client.post("/hypotheses", json=hypothesis_payload)
    assert response.status_code == 201, response.text
    return response.json()

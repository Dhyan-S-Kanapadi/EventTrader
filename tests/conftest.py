import json
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine

from eventtrader.persistence.database import create_database_engine
from eventtrader.settings import Settings

ROOT = Path(__file__).resolve().parents[1]


def pytest_addoption(parser):
    parser.addoption("--postgres", action="store_true", help="Run PostgreSQL integration tests")
    parser.addoption(
        "--postgres-port",
        type=int,
        default=None,
        help="Override the PostgreSQL port from .env for integration tests",
    )


@pytest.fixture
def gamma_payload():
    return json.loads((ROOT / "tests/fixtures/gamma_market.json").read_text(encoding="utf-8"))


@pytest.fixture
def book_payload():
    return json.loads((ROOT / "tests/fixtures/clob_book.json").read_text(encoding="utf-8"))


@pytest.fixture
def pg_engine(request, isolated_configuration):
    if not request.config.getoption("--postgres"):
        pytest.skip("Pass --postgres to run isolated-schema PostgreSQL tests")
    settings = Settings(_env_file=ROOT / ".env")
    if port := request.config.getoption("--postgres-port"):
        settings = settings.model_copy(update={"postgres_port": port})
    admin = create_database_engine(settings)
    schema = "eventtrader_test_" + uuid4().hex
    with admin.begin() as connection:
        connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    engine = create_engine(
        admin.url, connect_args={"options": f"-csearch_path={schema}", "connect_timeout": 3}
    )
    try:
        config = Config(str(ROOT / "alembic.ini"))
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
        admin.dispose()


@pytest.fixture(autouse=True)
def isolated_configuration(monkeypatch, tmp_path):
    """Tests must not inherit local credentials or configuration."""
    monkeypatch.chdir(tmp_path)
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
        monkeypatch.delenv(name.lower(), raising=False)
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")

import logging

from sqlalchemy import URL, Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from eventtrader.settings import Settings

logger = logging.getLogger(__name__)


def create_database_engine(settings: Settings) -> Engine:
    url = URL.create(
        "postgresql+psycopg",
        username=settings.postgres_user,
        password=settings.postgres_password.get_secret_value(),
        host=settings.postgres_host,
        port=settings.postgres_port,
        database=settings.postgres_db,
    )
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=2,
        max_overflow=0,
        pool_timeout=3,
        connect_args={"connect_timeout": 3, "options": "-c statement_timeout=3000"},
        hide_parameters=True,
    )


def check_database(engine: Engine) -> bool:
    try:
        with engine.connect() as connection:
            return bool(connection.execute(text("SELECT 1")).scalar_one() == 1)
    except SQLAlchemyError:
        logger.warning("database_readiness_failed")
        return False

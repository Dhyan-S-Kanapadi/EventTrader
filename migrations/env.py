"""Runtime settings supply credentials; no URL is stored in migration config."""

from alembic import context

from eventtrader.persistence.database import create_database_engine
from eventtrader.persistence.models import Base
from eventtrader.settings import Settings

if context.is_offline_mode():
    context.configure(dialect_name="postgresql", target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    provided_connection = context.config.attributes.get("connection")
    if provided_connection is not None:
        context.configure(connection=provided_connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
    else:
        engine = create_database_engine(Settings())
        try:
            with engine.connect() as connection:
                context.configure(connection=connection, target_metadata=Base.metadata)
                with context.begin_transaction():
                    context.run_migrations()
        finally:
            engine.dispose()

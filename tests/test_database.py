from unittest.mock import MagicMock

from sqlalchemy.exc import OperationalError

from eventtrader.logging import configure_logging
from eventtrader.persistence.database import check_database, create_database_engine
from eventtrader.settings import Settings


def test_database_probe_executes_only_select_one():
    engine = MagicMock()
    connection = engine.connect.return_value.__enter__.return_value
    connection.execute.return_value.scalar_one.return_value = 1
    assert check_database(engine) is True
    assert str(connection.execute.call_args.args[0]) == "SELECT 1"
    engine.connect.return_value.__exit__.assert_called_once()


def test_database_failure_does_not_log_exception_credentials(capsys):
    configure_logging("INFO")
    engine = MagicMock()
    engine.connect.side_effect = OperationalError("secret-sentinel", {}, Exception("password"))
    assert check_database(engine) is False
    output = capsys.readouterr().out
    assert "database_readiness_failed" in output
    assert "secret-sentinel" not in output
    assert "password" not in output


def test_engine_keeps_special_characters_in_password(monkeypatch):
    monkeypatch.setenv("POSTGRES_PASSWORD", "test@:/#pass")
    engine = create_database_engine(Settings())
    try:
        assert engine.url.password == "test@:/#pass"
        assert "test@:/#pass" not in str(engine.url)
    finally:
        engine.dispose()

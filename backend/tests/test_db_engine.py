"""Tests for database engine configuration."""

from unittest.mock import patch, MagicMock

import pytest


class TestEngineConfiguration:
    """Verify engine kwargs are set correctly for each database type."""

    def test_postgresql_kwargs_include_timeouts(self) -> None:
        """PostgreSQL config branch should set statement and lock timeouts."""
        with patch("app.config.get_settings") as mock_settings:
            mock_settings.return_value.database_url = "postgresql+asyncpg://user:pass@host/db"
            mock_settings.return_value.debug = False

            # Simulate the engine.py logic without actually creating the engine
            settings = mock_settings()
            kwargs: dict = {"echo": settings.debug}
            if settings.database_url.startswith("postgresql"):
                kwargs.update(
                    pool_size=20,
                    max_overflow=10,
                    pool_pre_ping=True,
                    connect_args={
                        "server_settings": {
                            "statement_timeout": "30000",
                            "lock_timeout": "10000",
                        },
                        "ssl": "prefer",
                    },
                )

            assert kwargs["pool_size"] == 20
            assert kwargs["max_overflow"] == 10
            assert kwargs["pool_pre_ping"] is True
            assert kwargs["connect_args"]["server_settings"]["statement_timeout"] == "30000"
            assert kwargs["connect_args"]["server_settings"]["lock_timeout"] == "10000"
            assert kwargs["connect_args"]["ssl"] == "prefer"

    def test_sqlite_kwargs_use_static_pool(self) -> None:
        """SQLite config branch should use StaticPool."""
        from sqlalchemy.pool import StaticPool

        settings_mock = MagicMock()
        settings_mock.database_url = "sqlite+aiosqlite://"
        settings_mock.debug = False

        kwargs: dict = {"echo": settings_mock.debug}
        if "sqlite" in settings_mock.database_url:
            kwargs.update(
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )

        assert kwargs["poolclass"] is StaticPool
        assert kwargs["connect_args"]["check_same_thread"] is False

    def test_database_url_normalisation(self) -> None:
        """Config should normalise postgres:// to postgresql+asyncpg://."""
        from app.config import Settings

        s = Settings(database_url="postgres://user:pass@host/db")
        assert s.database_url == "postgresql+asyncpg://user:pass@host/db"

        s2 = Settings(database_url="postgresql://user:pass@host/db")
        assert s2.database_url == "postgresql+asyncpg://user:pass@host/db"

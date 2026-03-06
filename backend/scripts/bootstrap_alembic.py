"""Bootstrap Alembic for legacy databases, then migrate to head.

This handles the transition from startup-time ``create_all()`` schema creation
to Alembic-managed migrations. If a database already has the base tables but no
``alembic_version`` row, we stamp it at revision ``001`` so migrations can
continue from the first tracked schema revision.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings


async def _inspect_database() -> tuple[bool, bool, str | None]:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)

    try:
        async with engine.connect() as conn:
            alembic_exists = bool(
                await conn.scalar(text("SELECT to_regclass('public.alembic_version') IS NOT NULL"))
            )
            organisations_exists = bool(
                await conn.scalar(text("SELECT to_regclass('public.organisations') IS NOT NULL"))
            )
            users_id_type = await conn.scalar(
                text(
                    """
                    SELECT data_type
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'users'
                      AND column_name = 'id'
                    """
                )
            )
    finally:
        await engine.dispose()

    return alembic_exists, organisations_exists, users_id_type


def _alembic_config() -> Config:
    backend_dir = Path(__file__).resolve().parents[1]
    return Config(str(backend_dir / "alembic.ini"))


def main() -> None:
    alembic_exists, organisations_exists, users_id_type = asyncio.run(_inspect_database())
    config = _alembic_config()

    if not alembic_exists and organisations_exists:
        print(
            "Legacy schema detected without alembic_version; "
            f"stamping revision 001 (users.id type: {users_id_type or 'unknown'})."
        )
        command.stamp(config, "001")

    command.upgrade(config, "head")


if __name__ == "__main__":
    main()

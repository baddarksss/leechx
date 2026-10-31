"""موتور دیتابیس و نشست‌ها (SQLAlchemy 2.x async).

پیش‌فرض SQLite است تا نصب و اجرا ساده باشد. برای چند سرور / کاربر زیاد
کافی است ``DATABASE_URL`` را به Postgres تغییر بدهی؛ هیچ کد دیگری عوض نمی‌شود.
"""
from __future__ import annotations

import logging

from sqlalchemy import Column, event, inspect, text
from sqlalchemy.engine import Dialect
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.config import Config, get_config
from app.db.models import Base

log = logging.getLogger("leechx.db")

_engine: AsyncEngine | None = None
_factory: async_sessionmaker[AsyncSession] | None = None


def build_engine(cfg: Config) -> AsyncEngine:
    url = cfg.sqlalchemy_url
    kwargs: dict = {"echo": False, "future": True, "pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"timeout": 30}
    else:
        kwargs["pool_size"] = 10
        kwargs["max_overflow"] = 20
    engine = create_async_engine(url, **kwargs)

    if url.startswith("sqlite"):
        @event.listens_for(engine.sync_engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover - وابسته به درایور
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA busy_timeout=30000")
            cur.close()

    return engine


def engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = build_engine(get_config())
    if _engine is None:  # pragma: no cover
        raise RuntimeError("engine ساخته نشد")
    return _engine


def session_factory() -> async_sessionmaker[AsyncSession]:
    global _factory
    if _factory is None:
        _factory = async_sessionmaker(engine(), expire_on_commit=False, class_=AsyncSession)
    return _factory


def session() -> AsyncSession:
    """``async with session() as s:``"""
    return session_factory()()


def _migrate_user_language_selected(sync_conn) -> None:
    """Add onboarding and per-user delivery settings to older databases safely."""
    inspector = inspect(sync_conn)
    if "users" not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns("users")}
    boolean_default = "0" if sync_conn.dialect.name == "sqlite" else "FALSE"
    additions = {
        "language_selected": ("BOOLEAN", boolean_default),
        "uploads": ("INTEGER", "0"),
        "default_mode": ("VARCHAR(16)", "'video'"),
        "default_destination": ("VARCHAR(16)", "'telegram'"),
    }
    for name, (column_type, default) in additions.items():
        if name in columns:
            continue
        sync_conn.execute(text(
            f"ALTER TABLE users ADD COLUMN {name} {column_type} NOT NULL DEFAULT {default}"
        ))


def _column_default_sql(column: Column, dialect: Dialect) -> str | None:
    """مقدار پیش‌فرض ستون را به SQL قابل‌نوشتن تبدیل می‌کند (یا None)."""
    if column.server_default is not None:
        arg = getattr(column.server_default, "arg", None)
        if arg is not None and not callable(arg):
            return str(arg)
    default = column.default
    if default is None or not getattr(default, "is_scalar", False):
        return None
    value = default.arg
    if callable(value):
        return None
    if isinstance(value, bool):
        if dialect.name == "sqlite":
            return "1" if value else "0"
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    return None


def _migrate_missing_columns(sync_conn) -> None:
    """هر ستونی که در مدل هست ولی در جدولِ موجود نیست را اضافه می‌کند.

    ``create_all`` فقط جدول‌های جدید را می‌سازد؛ ستون‌های تازه در جدول‌های قدیمی
    باعث می‌شوند ربات بعد از هر آپدیتِ سورس بشکند. این تابع یک مایگریشن افزایشی
    سبک است: فقط ADD COLUMN انجام می‌دهد و دادهٔ موجود را دست نمی‌زند.
    """
    inspector = inspect(sync_conn)
    existing_tables = set(inspector.get_table_names())
    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue
        present = {col["name"] for col in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in present or column.primary_key:
                continue
            ddl_type = column.type.compile(dialect=sync_conn.dialect)
            default_sql = _column_default_sql(column, sync_conn.dialect)
            statement = f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {ddl_type}'
            if default_sql is not None:
                statement += f" DEFAULT {default_sql}"
            if not column.nullable:
                if default_sql is None:
                    log.warning(
                        "cannot add NOT NULL column %s.%s without a default; skipping",
                        table.name,
                        column.name,
                    )
                    continue
                statement += " NOT NULL"
            try:
                sync_conn.execute(text(statement))
                log.info("added missing column %s.%s", table.name, column.name)
            except Exception:  # noqa: BLE001 — مایگریشن نباید ربات را بخواباند
                log.warning("could not add column %s.%s", table.name, column.name, exc_info=True)


async def init_db(cfg: Config | None = None) -> None:
    global _engine, _factory
    cfg = cfg or get_config()
    cfg.ensure_dirs()
    if _engine is None:
        _engine = build_engine(cfg)
    _factory = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_migrate_user_language_selected)
        await conn.run_sync(_migrate_missing_columns)
        # SQLite and PostgreSQL both support this atomic singleton bootstrap.
        await conn.execute(text(
            "INSERT INTO traffic_counters (id) VALUES (1) ON CONFLICT (id) DO NOTHING"
        ))


async def dispose_db() -> None:
    global _engine, _factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _factory = None


async def healthcheck() -> bool:
    try:
        async with session() as s:
            await s.execute(text("SELECT 1"))
        return True
    except Exception:
        return False

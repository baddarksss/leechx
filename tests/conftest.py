"""فیکسچرهای مشترک تست."""
from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio

from app.config import get_config
from app.db import base as db_base


@pytest.fixture()
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("LINK_SECRET", "test-secret")
    monkeypatch.setenv("PUBLIC_BASE_URL", "http://localhost:8080")
    get_config.cache_clear()
    conf = get_config()
    conf.ensure_dirs()
    yield conf
    get_config.cache_clear()


@pytest_asyncio.fixture()
async def db(cfg):
    await db_base.init_db(cfg)
    yield cfg
    await db_base.dispose_db()


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

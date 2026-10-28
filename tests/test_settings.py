import pytest

from app.services.runtime_settings import RuntimeSettings


@pytest.mark.asyncio
async def test_defaults_from_env(db):
    settings = RuntimeSettings(db)
    await settings.load()
    assert settings.ttl_hours == pytest.approx(6.0)
    assert settings.maintenance is False
    assert settings.rate_limit_seconds >= 0


@pytest.mark.asyncio
async def test_set_and_persist(db):
    settings = RuntimeSettings(db)
    await settings.load()
    await settings.set("link_ttl_hours", 2.5)
    assert settings.ttl_hours == pytest.approx(2.5)
    assert settings.ttl_seconds == 9000

    fresh = RuntimeSettings(db)
    await fresh.load()
    assert fresh.get_float("link_ttl_hours") == pytest.approx(2.5)


@pytest.mark.asyncio
async def test_bool_toggle(db):
    settings = RuntimeSettings(db)
    await settings.load()
    assert settings.maintenance is False
    assert await settings.toggle("maintenance") is True
    assert settings.maintenance is True
    assert await settings.toggle("maintenance") is False
    assert settings.maintenance is False


@pytest.mark.asyncio
async def test_bad_values_fall_back(db):
    settings = RuntimeSettings(db)
    await settings.load()
    await settings.set("max_upload_mb", "abc")
    assert settings.get_int("max_upload_mb") == 2000  # پیش‌فرض env
    with pytest.raises(KeyError):
        await settings.set("does_not_exist", 1)


@pytest.mark.asyncio
async def test_snapshot(db):
    settings = RuntimeSettings(db)
    await settings.load()
    snap = settings.snapshot()
    assert set(snap) == {
        "link_ttl_hours",
        "max_upload_mb",
        "max_link_mb",
        "rate_limit_seconds",
        "daily_quota",
        "maintenance",
        "nsfw_enabled",
    }

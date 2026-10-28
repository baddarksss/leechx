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


@pytest.mark.asyncio
async def test_runtime_values_and_masking(db):
    settings = RuntimeSettings(db)
    await settings.load()

    assert settings.get_str("telegram_api_url") == ""
    assert settings.get_optional_int("admin_group_id") is None
    assert settings.masked("telegram_api_hash") == "—"

    await settings.set("telegram_api_url", "http://127.0.0.1:8081")
    await settings.set("telegram_api_hash", "secret-hash")
    await settings.set("admin_group_id", "-1001234567890")
    await settings.set("public_base_url", "https://files.example.com")

    assert settings.masked("telegram_api_hash") == "••••••"
    assert settings.get_optional_int("admin_group_id") == -1001234567890

    settings.apply_to_config()
    assert db.telegram_api_url == "http://127.0.0.1:8081"
    assert db.telegram_api_hash == "secret-hash"
    assert db.public_base_url == "https://files.example.com"


@pytest.mark.asyncio
async def test_owner_from_settings_applies_only_without_env_owner(db, monkeypatch):
    monkeypatch.setenv("OWNER_IDS", "")
    db.owner_ids = ""
    settings = RuntimeSettings(db)
    await settings.load()
    await settings.set("owner_id", "42")
    settings.apply_to_config()
    assert db.owners == [42]

    db.owner_ids = "7"
    settings.apply_to_config()
    assert db.owners == [7]


@pytest.mark.asyncio
async def test_admin_group_configure_without_bot(db):
    from app.services.admin_group import AdminGroup

    settings = RuntimeSettings(db)
    await settings.load()
    hub = AdminGroup(db, settings)

    assert hub.configured is False
    created = await hub.configure(123, "Team")
    assert set(created) == {"downloads", "uploads", "reports", "logs"}
    assert all(value is None for value in created.values())
    assert hub.configured is True
    assert hub.chat_id == 123
    assert hub.title == "Team"
    assert await hub.send("logs", "hello") is False

    await hub.disable()
    assert hub.configured is False
    assert hub.title == ""

"""دیپلوی ZIP + API موقت عیب‌یابی (توکن زمان‌دار و محدودهٔ دسترسی)."""
from __future__ import annotations

import io
import json
import time
import zipfile
from pathlib import Path

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from app.db import repo
from app.services.debug_access import MAX_HOURS, DebugAccess, hash_token
from app.services.runtime_settings import RuntimeSettings
from app.services.updater import SourceUpdater

VERSION_SOURCE = '__version__ = "9.9.9"\nCODENAME = "Test"\n'


def make_source(root: Path) -> Path:
    (root / "app").mkdir(parents=True, exist_ok=True)
    (root / "app" / "version.py").write_text(VERSION_SOURCE, encoding="utf-8")
    (root / "app" / "service.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "main.py").write_text("print('hello')\n", encoding="utf-8")
    (root / "README.md").write_text("# demo\n", encoding="utf-8")
    (root / ".env").write_text("BOT_TOKEN=secret\n", encoding="utf-8")
    (root / "data").mkdir(exist_ok=True)
    (root / "data" / "db.sqlite").write_text("private", encoding="utf-8")
    return root


def build_zip(path: Path, *, prefix: str = "", extra: dict[str, str] | None = None) -> Path:
    files = {
        "main.py": "print('new')\n",
        "app/version.py": VERSION_SOURCE,
        "app/new_feature.py": "NEW = True\n",
        "CHANGELOG.md": "# Changelog\n",
    }
    files.update(extra or {})
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, body in files.items():
            zf.writestr(f"{prefix}{name}", body)
    path.write_bytes(buffer.getvalue())
    return path


# ── export / inspect / apply ────────────────────────────────
def test_export_zip_skips_private_files(cfg, tmp_path):
    root = make_source(tmp_path / "src")
    updater = SourceUpdater(cfg, root=root)
    archive = updater.export_zip()

    assert archive.is_file()
    with zipfile.ZipFile(archive) as zf:
        names = set(zf.namelist())
    assert "main.py" in names
    assert "app/version.py" in names
    assert not any(name.startswith("data/") for name in names)
    assert ".env" not in names


def test_inspect_zip_detects_version_and_prefix(cfg, tmp_path):
    root = make_source(tmp_path / "src")
    updater = SourceUpdater(cfg, root=root)
    archive = build_zip(tmp_path / "update.zip", prefix="leechx-main/")

    preview = updater.inspect_zip(archive)
    assert preview.ok, preview.reason
    assert preview.prefix == "leechx-main/"
    assert preview.version == "9.9.9"
    assert preview.files == 4
    assert preview.is_newer is True


def test_inspect_zip_rejects_missing_entrypoints(cfg, tmp_path):
    root = make_source(tmp_path / "src")
    updater = SourceUpdater(cfg, root=root)
    # main.py و app/version.py عمداً در آرشیو نیستند.
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("notes.txt", "nothing")
    archive = tmp_path / "bad.zip"
    archive.write_bytes(buffer.getvalue())

    preview = updater.inspect_zip(archive)
    assert preview.ok is False
    assert "main.py" in preview.reason


def test_inspect_zip_rejects_path_traversal(cfg, tmp_path):
    root = make_source(tmp_path / "src")
    updater = SourceUpdater(cfg, root=root)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("../evil.py", "bad")
        zf.writestr("main.py", "ok")
        zf.writestr("app/version.py", VERSION_SOURCE)
    archive = tmp_path / "traversal.zip"
    archive.write_bytes(buffer.getvalue())

    preview = updater.inspect_zip(archive)
    assert preview.ok is False
    assert "unsafe path" in preview.reason


def test_inspect_zip_rejects_non_zip(cfg, tmp_path):
    root = make_source(tmp_path / "src")
    updater = SourceUpdater(cfg, root=root)
    archive = tmp_path / "fake.zip"
    archive.write_text("not a zip", encoding="utf-8")
    preview = updater.inspect_zip(archive)
    assert preview.ok is False
    assert "not a ZIP" in preview.reason


def test_apply_zip_writes_source_backs_up_and_ignores_private_paths(cfg, tmp_path):
    target = make_source(tmp_path / "target")
    updater = SourceUpdater(cfg, root=target)
    archive = build_zip(
        tmp_path / "update.zip",
        extra={".env": "BOT_TOKEN=hacked\n", "data/db.sqlite": "hacked"},
    )

    result = updater.apply_zip(archive)

    assert result.ok, result.reason
    assert result.version == "9.9.9"
    assert result.backup is not None and Path(result.backup).is_file()
    assert (target / "app" / "new_feature.py").is_file()
    assert (target / ".env").read_text(encoding="utf-8") == "BOT_TOKEN=secret\n"
    assert (target / "data" / "db.sqlite").read_text(encoding="utf-8") == "private"
    last = updater.last_update()
    assert last["version"] == "9.9.9"
    assert last["files"] >= 4


def test_apply_zip_strips_single_top_level_folder(cfg, tmp_path):
    target = make_source(tmp_path / "target")
    updater = SourceUpdater(cfg, root=target)
    archive = build_zip(tmp_path / "update.zip", prefix="LechX-fork/")

    result = updater.apply_zip(archive)

    assert result.ok, result.reason
    assert (target / "app" / "new_feature.py").is_file()
    assert not (target / "LechX-fork").exists()


def test_apply_zip_rejects_incomplete_archive_without_touching_source(cfg, tmp_path):
    target = make_source(tmp_path / "target")
    updater = SourceUpdater(cfg, root=target)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("main.py", "print('x')")
    archive = tmp_path / "incomplete.zip"
    archive.write_bytes(buffer.getvalue())

    result = updater.apply_zip(archive)
    assert result.ok is False
    assert result.backup is None
    assert (target / "app" / "service.py").is_file()
    assert updater.last_update() == {}


def test_updater_stats_contains_version_and_backup_info(cfg, tmp_path):
    root = make_source(tmp_path / "src")
    updater = SourceUpdater(cfg, root=root)
    stats = updater.stats()
    assert stats["version"]
    assert stats["files"] >= 3
    assert stats["backup"] == "—"


# ── debug tokens ────────────────────────────────────────────
async def make_debug(cfg, tmp_path, *, enabled: bool = True):
    root = make_source(tmp_path / "source")
    settings = RuntimeSettings(cfg)
    await settings.load()
    # پیش‌فرض سورس روشن است؛ برای تستِ حالت خاموش باید صریحاً خاموش شود.
    await settings.set("debug_enabled", enabled)
    updater = SourceUpdater(cfg, root=root)
    debug = DebugAccess(cfg, settings, updater)
    application = web.Application()
    debug.register(application)
    return debug, settings, updater, application


@pytest.mark.asyncio
async def test_token_ttl_is_capped_and_scopes_are_normalized(db, tmp_path):
    debug, _settings, _updater, _app = await make_debug(db, tmp_path)

    raw, row = await debug.create(1, hours=999, scopes="restart, read")
    assert raw.startswith("lxdbg_")
    assert row.token_hash == hash_token(raw)
    assert raw not in row.token_hash
    assert row.scopes == "read,write,restart"
    assert row.expires_at <= int(time.time()) + MAX_HOURS * 3600 + 5
    assert row.expires_at > int(time.time()) + (MAX_HOURS - 1) * 3600

    _, read_row = await debug.create(1, hours=0, scopes="unknown")
    assert read_row.scopes == "read"
    assert read_row.expires_at <= int(time.time()) + 3600


def test_scope_hierarchy_is_cumulative():
    """برچسب «read + write» و «full» باید واقعاً همان دسترسی را بدهد."""
    assert DebugAccess.normalize_scopes("write") == "read,write"
    assert DebugAccess.normalize_scopes("restart") == "read,write,restart"
    assert DebugAccess.granted_scopes("restart") == {"read", "write", "restart"}
    assert DebugAccess.granted_scopes("write") == {"read", "write"}
    assert DebugAccess.granted_scopes("read") == {"read"}
    assert DebugAccess.granted_scopes("") == set()


@pytest.mark.asyncio
async def test_debug_api_requires_token_and_read_scope(db, tmp_path):
    debug, _settings, _updater, application = await make_debug(db, tmp_path)
    raw, _row = await debug.create(1, hours=1, scopes="read")

    async with TestClient(TestServer(application)) as client:
        assert (await client.get("/debug/health")).status == 401

        headers = {"Authorization": f"Bearer {raw}"}
        health = await client.get("/debug/health", headers=headers)
        assert health.status == 200
        payload = await health.json()
        assert payload["version"]
        assert payload["debug_enabled"] is True

        state = await client.get("/debug/state", headers=headers)
        assert state.status == 200
        state_payload = await state.json()
        assert state_payload["version"] == payload["version"]

        listing = await client.get("/debug/source", headers=headers)
        assert listing.status == 200
        names = (await listing.json())["files"]
        assert "app/version.py" in names

        file_resp = await client.get("/debug/source?path=app/version.py", headers=headers)
        assert file_resp.status == 200
        file_payload = await file_resp.json()
        assert "__version__" in file_payload["content"]

        traversal = await client.get("/debug/source?path=../../etc/passwd", headers=headers)
        assert traversal.status == 400

        write_denied = await client.post(
            "/debug/source",
            headers=headers,
            json={"path": "app/new_feature.py", "content": "X = 1\n"},
        )
        assert write_denied.status == 403

        restart_denied = await client.post("/debug/restart", headers=headers)
        assert restart_denied.status == 403


@pytest.mark.asyncio
async def test_debug_api_write_scope_and_path_guard(db, tmp_path):
    debug, _settings, updater, application = await make_debug(db, tmp_path)
    raw, _row = await debug.create(1, hours=1, scopes="write")
    headers = {"Authorization": f"Bearer {raw}"}

    async with TestClient(TestServer(application)) as client:
        ok = await client.post(
            "/debug/source",
            headers=headers,
            json={"files": {"app/new_feature.py": "X = 1\n", "tests/test_new.py": "def test(): pass\n"}},
        )
        assert ok.status == 200
        body = await ok.json()
        assert body["restart_required"] is True
        assert (updater.root / "app" / "new_feature.py").read_text(encoding="utf-8") == "X = 1\n"

        for bad_path in (".env", "data/db.sqlite", "../evil.py", "app/../../evil.py"):
            denied = await client.post(
                "/debug/source",
                headers=headers,
                json={"path": bad_path, "content": "bad"},
            )
            assert denied.status == 400, bad_path

        assert not (updater.root / "data" / "db.sqlite").read_text(encoding="utf-8").startswith("bad")
        assert (updater.root / ".env").read_text(encoding="utf-8").startswith("BOT_TOKEN=secret")

        restart = await client.post("/debug/restart", headers=headers)
        assert restart.status == 403  # write ≠ restart


@pytest.mark.asyncio
async def test_full_token_can_read_write_and_restart(db, tmp_path):
    """توکن «کامل» باید read و write را هم داشته باشد (قبلاً فقط restart بود)."""
    debug, _settings, updater, application = await make_debug(db, tmp_path)
    raw, row = await debug.create(1, hours=1, scopes="restart")
    assert row.scopes == "read,write,restart"
    headers = {"Authorization": f"Bearer {raw}"}

    async with TestClient(TestServer(application)) as client:
        assert (await client.get("/debug/health", headers=headers)).status == 200
        logs = await client.get("/debug/logs?limit=2", headers=headers)
        assert logs.status == 200
        source = await client.get("/debug/source?path=main.py", headers=headers)
        assert source.status == 200

        written = await client.post(
            "/debug/source",
            headers=headers,
            json={"path": "app/full_scope.py", "content": "Y = 2\n"},
        )
        assert written.status == 200
        assert (updater.root / "app" / "full_scope.py").read_text(encoding="utf-8") == "Y = 2\n"


@pytest.mark.asyncio
async def test_debug_api_rejects_expired_and_revoked_tokens(db, tmp_path):
    debug, _settings, _updater, application = await make_debug(db, tmp_path)

    raw, row = await debug.create(1, hours=1, scopes="read")
    expired_raw = "lxdbg_expired"
    await repo.create_debug_token(
        hash_token(expired_raw),
        label="test",
        scopes="read",
        created_by=1,
        expires_at=int(time.time()) - 5,
    )

    async with TestClient(TestServer(application)) as client:
        expired = await client.get(
            "/debug/health", headers={"Authorization": f"Bearer {expired_raw}"}
        )
        assert expired.status == 401
        assert "expired" in (await expired.json())["error"]

        assert await debug.revoke(row.id) is True
        revoked = await client.get("/debug/health", headers={"Authorization": f"Bearer {raw}"})
        assert revoked.status == 401


@pytest.mark.asyncio
async def test_debug_api_is_off_unless_enabled(db, tmp_path):
    debug, settings, _updater, application = await make_debug(db, tmp_path, enabled=False)
    raw, _row = await debug.create(1, hours=1, scopes="read")
    assert settings.debug_enabled is False

    async with TestClient(TestServer(application)) as client:
        resp = await client.get("/debug/health", headers={"Authorization": f"Bearer {raw}"})
        assert resp.status == 403
        assert "disabled" in (await resp.json())["error"]


@pytest.mark.asyncio
async def test_debug_api_ip_allow_list(db, tmp_path):
    debug, settings, _updater, application = await make_debug(db, tmp_path)
    raw, _row = await debug.create(1, hours=1, scopes="read")
    await settings.set("debug_ip_allow", "10.9.9.9")

    async with TestClient(TestServer(application)) as client:
        resp = await client.get("/debug/health", headers={"Authorization": f"Bearer {raw}"})
        assert resp.status == 403
        assert "allow-listed" in (await resp.json())["error"]

        await settings.set("debug_ip_allow", "127.0.0.1")
        resp = await client.get("/debug/health", headers={"Authorization": f"Bearer {raw}"})
        assert resp.status == 200


@pytest.mark.asyncio
async def test_revoke_all_and_purge(db, tmp_path):
    debug, _settings, _updater, _app = await make_debug(db, tmp_path)
    await debug.create(1, hours=1, scopes="read")
    await debug.create(2, hours=1, scopes="write")

    assert len(await debug.active()) == 2
    assert await debug.revoke_all() == 2
    assert await debug.active() == []
    purged = await repo.purge_debug_tokens()
    assert purged >= 2


@pytest.mark.asyncio
async def test_last_update_json_is_valid(db, tmp_path):
    debug, _settings, updater, _app = await make_debug(db, tmp_path)
    _raw, _row = await debug.create(1, hours=1, scopes="read")
    archive = build_zip(tmp_path / "update.zip")
    assert updater.apply_zip(archive).ok is True
    raw = json.loads((updater.workdir / "last_update.json").read_text(encoding="utf-8"))
    assert raw["version"] == "9.9.9"

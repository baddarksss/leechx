"""آپدیت پایدار: حذف فایل منسوخ، نصب وابستگی، ایندکس اجباری و مایگریشن ستون."""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from app.db.base import _migrate_missing_columns
from app.services.sites import SiteIndex
from app.services.updater import SourceUpdater

VERSION_SOURCE = '__version__ = "9.9.9"\nCODENAME = "Test"\n'


def make_source(root: Path) -> Path:
    (root / "app").mkdir(parents=True, exist_ok=True)
    (root / "app" / "version.py").write_text(VERSION_SOURCE, encoding="utf-8")
    (root / "app" / "old.py").write_text("OLD = 1\n", encoding="utf-8")
    (root / "app" / "keep.py").write_text("KEEP = 1\n", encoding="utf-8")
    (root / "main.py").write_text("print('hi')\n", encoding="utf-8")
    (root / "requirements.txt").write_text("aiohttp>=3.11\n", encoding="utf-8")
    return root


def raw_zip(path: Path, files: dict[str, str]) -> Path:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, body in files.items():
            zf.writestr(name, body)
    path.write_bytes(buffer.getvalue())
    return path


def build_zip(path: Path, *, files: dict[str, str] | None = None) -> Path:
    base = {
        "main.py": "print('hi')\n",
        "app/version.py": VERSION_SOURCE,
        "app/keep.py": "KEEP = 2\n",
        "requirements.txt": "aiohttp>=3.11\n",
    }
    base.update(files or {})
    return raw_zip(path, base)


# ── فایل‌های منسوخ ───────────────────────────────────────────
def test_apply_zip_removes_files_missing_from_archive(cfg, tmp_path):
    root = make_source(tmp_path / "src")
    updater = SourceUpdater(cfg, root=root)

    result = updater.apply_zip(build_zip(tmp_path / "u.zip"))

    assert result.ok, result.reason
    assert result.removed == 1
    assert not (root / "app" / "old.py").exists()
    assert (root / "app" / "keep.py").read_text(encoding="utf-8") == "KEEP = 2\n"
    last = updater.last_update()
    assert last["removed"] == 1


def test_apply_zip_rejects_truncated_archive(cfg, tmp_path):
    root = make_source(tmp_path / "src")
    updater = SourceUpdater(cfg, root=root)
    archive = raw_zip(
        tmp_path / "tiny.zip",
        {"main.py": "print('hi')\n", "app/version.py": VERSION_SOURCE},
    )

    result = updater.apply_zip(archive)

    assert result.ok is False
    assert "incomplete" in result.reason
    assert (root / "app" / "old.py").is_file()
    assert updater.last_update() == {}


def test_apply_zip_rejects_broken_python(cfg, tmp_path):
    root = make_source(tmp_path / "src")
    updater = SourceUpdater(cfg, root=root)
    archive = build_zip(tmp_path / "bad.zip", files={"app/broken.py": "def oops(:\n"})

    result = updater.apply_zip(archive)

    assert result.ok is False
    assert "syntax" in result.reason
    assert (root / "app" / "old.py").is_file()
    assert updater.last_update() == {}


def test_apply_zip_does_not_copy_pycache(cfg, tmp_path):
    root = make_source(tmp_path / "src")
    updater = SourceUpdater(cfg, root=root)

    result = updater.apply_zip(build_zip(tmp_path / "u.zip"))

    assert result.ok, result.reason
    assert not list(root.rglob("*.pyc"))
    assert result.files == 4


# ── وابستگی‌ها ──────────────────────────────────────────────
def test_requirements_changed_detects_new_lines(cfg, tmp_path):
    root = make_source(tmp_path / "src")
    updater = SourceUpdater(cfg, root=root)
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "requirements.txt").write_text("aiohttp>=3.11\n", encoding="utf-8")
    assert updater.requirements_changed(staging) is False

    (staging / "requirements.txt").write_text("aiohttp>=3.11\nnewpkg>=1\n", encoding="utf-8")
    assert updater.requirements_changed(staging) is True


def test_apply_zip_aborts_when_dependency_install_fails(cfg, tmp_path, monkeypatch):
    root = make_source(tmp_path / "src")
    updater = SourceUpdater(cfg, root=root)
    seen: dict[str, Path] = {}

    def fake_install(path: Path) -> tuple[bool, str]:
        seen["path"] = path
        return False, "network down"

    monkeypatch.setattr(updater, "_install_requirements", fake_install)
    archive = build_zip(
        tmp_path / "deps.zip",
        files={"requirements.txt": "aiohttp>=3.11\nnewpkg>=1\n"},
    )

    result = updater.apply_zip(archive)

    assert result.ok is False
    assert "dependency" in result.reason
    assert seen["path"].name == "requirements.txt"
    assert (root / "app" / "old.py").is_file()
    assert updater.last_update() == {}


# ── ایندکس سایت‌ها ──────────────────────────────────────────
def test_site_index_force_rebuild(monkeypatch):
    class FakeIE:
        IE_NAME = "fake"
        IE_DESC = "fake site"

        @classmethod
        def suitable(cls, url: str) -> bool:  # pragma: no cover - ساده
            return "fake" in url

    calls = {"n": 0}

    def fake_gen():
        calls["n"] += 1
        return [FakeIE]

    import yt_dlp.extractor as extractor

    monkeypatch.setattr(extractor, "gen_extractor_classes", fake_gen)

    index = SiteIndex()
    index.build()
    assert index.count == 1
    index.build()
    assert calls["n"] == 1  # بدون force دوباره ساخته نمی‌شود
    index.build(force=True)
    assert calls["n"] == 2


# ── مایگریشن دیتابیس ────────────────────────────────────────
def test_missing_columns_are_added_to_old_tables(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'old.db').as_posix()}")
    try:
        with engine.begin() as conn:
            conn.execute(text('CREATE TABLE users (id INTEGER PRIMARY KEY, lang VARCHAR(8))'))
            _migrate_missing_columns(conn)
            columns = {col["name"] for col in inspect(conn).get_columns("users")}
    finally:
        engine.dispose()

    assert {"language_selected", "uploads", "default_mode", "default_destination"} <= columns

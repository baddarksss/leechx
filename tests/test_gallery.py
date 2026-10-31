"""موتور گالری: تشخیص، دانلود، آلبوم تلگرام و ZIP برای لینک مستقیم."""
from __future__ import annotations

import asyncio
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core import errors
from app.services import gallery
from app.services.downloader import Downloader, DownloadResult, MediaInfo, Progress
from app.services.formats import FormatOption
from app.services.jobs import JobManager, apply_custom_name
from app.services.uploader import Uploader


def make_jpeg(path: Path, payload: bytes = b"img") -> Path:
    path.write_bytes(payload)
    return path


# ── خود موتور ────────────────────────────────────────────────
def test_display_title_uses_url_tail():
    assert gallery.display_title("https://x.com/user/status/123/photo-1") == "photo-1"
    assert gallery.display_title("https://site.tld/p/great_post.jpg") == "great_post"


def test_collect_skips_non_media_and_empty_files(tmp_path):
    make_jpeg(tmp_path / "a.jpg")
    make_jpeg(tmp_path / "b.PNG")
    (tmp_path / "c.json").write_text("{}", encoding="utf-8")
    (tmp_path / "d.jpg.part").write_bytes(b"partial")
    (tmp_path / "empty.jpg").write_bytes(b"")
    (tmp_path / "sub").mkdir()
    make_jpeg(tmp_path / "sub" / "e.webp")

    found = gallery._collect(tmp_path)

    assert [p.name for p in found] == ["a.jpg", "b.PNG", "e.webp"]


def test_natural_sort_keeps_album_order(tmp_path):
    for name in ("10.jpg", "2.jpg", "1.jpg"):
        make_jpeg(tmp_path / name)
    assert [p.name for p in gallery._collect(tmp_path)] == ["1.jpg", "2.jpg", "10.jpg"]


def test_supports_knows_instagram():
    if not gallery.available():
        pytest.skip("gallery-dl is not installed")
    assert gallery.supports("https://www.instagram.com/p/ABC123/")
    assert gallery.extractor_name("https://www.instagram.com/p/ABC123/") == "instagram"


# ── fallback در Downloader ───────────────────────────────────
@pytest.mark.asyncio
async def test_probe_falls_back_to_gallery_when_ytdlp_unsupported(cfg, monkeypatch):
    downloader = Downloader(cfg)

    def boom(self, url):
        raise errors.UnsupportedUrl("Unsupported URL")

    monkeypatch.setattr(Downloader, "_probe_blocking", boom)
    monkeypatch.setattr(gallery, "available", lambda: True)
    monkeypatch.setattr(gallery, "supports", lambda url: True)
    monkeypatch.setattr(gallery, "extractor_name", lambda url: "instagram")

    info = await downloader.probe("https://www.instagram.com/p/ABC123/")

    assert info.gallery is True
    assert info.extractor == "gallery-dl:instagram"
    assert info.title


@pytest.mark.asyncio
async def test_probe_keeps_error_when_gallery_does_not_support(cfg, monkeypatch):
    downloader = Downloader(cfg)

    def boom(self, url):
        raise errors.UnsupportedUrl("Unsupported URL")

    monkeypatch.setattr(Downloader, "_probe_blocking", boom)
    monkeypatch.setattr(gallery, "available", lambda: True)
    monkeypatch.setattr(gallery, "supports", lambda url: False)

    with pytest.raises(errors.UnsupportedUrl):
        await downloader.probe("https://unknown.invalid/x")


@pytest.mark.asyncio
async def test_download_gallery_returns_all_parts(cfg, tmp_path, monkeypatch):
    downloader = Downloader(cfg)
    first = make_jpeg(tmp_path / "1.jpg", b"aaa")
    second = make_jpeg(tmp_path / "2.jpg", b"bbb")

    async def fake_download(url, workdir, progress, cancel, **kwargs):
        return gallery.GalleryResult(
            paths=[first, second], title="My Post", extractor="instagram"
        )

    monkeypatch.setattr(gallery, "download", fake_download)
    info = MediaInfo(url="https://x/1", title="My Post", gallery=True)

    result = await downloader.download(
        info.url,
        FormatOption(kind="gallery", code="gallery", label="g", selector=""),
        tmp_path,
        Progress(),
        asyncio.Event(),
        info,
    )

    assert result.gallery is True
    assert result.parts == [first, second]
    assert result.path == first
    assert result.size == 6
    assert result.count == 2


# ── آپلود آلبوم ──────────────────────────────────────────────
class AlbumBot:
    def __init__(self) -> None:
        self.groups: list[list] = []
        self.documents: list[dict] = []
        self.photos: list[dict] = []

    async def send_media_group(self, chat_id, media):
        self.groups.append(list(media))
        return [SimpleNamespace(message_id=100 + len(self.groups))]

    async def send_document(self, **kwargs):
        self.documents.append(kwargs)
        return SimpleNamespace(message_id=200 + len(self.documents))

    async def send_photo(self, **kwargs):
        self.photos.append(kwargs)
        return SimpleNamespace(message_id=300 + len(self.photos))


def make_album(tmp_path, count: int, suffix: str = ".jpg") -> DownloadResult:
    parts = [
        make_jpeg(tmp_path / f"{i}{suffix}", b"x" * 10)
        for i in range(1, count + 1)
    ]
    mime = "image/jpeg" if suffix == ".jpg" else "application/octet-stream"
    return DownloadResult(
        path=parts[0],
        title="Album",
        mime=mime,
        size=sum(p.stat().st_size for p in parts),
        parts=parts,
        gallery=True,
    )


def gallery_uploader() -> Uploader:
    cfg = SimpleNamespace(uses_local_api=True)
    settings = SimpleNamespace(max_upload_bytes=2_000_000_000)
    return Uploader(cfg, settings)


@pytest.mark.asyncio
async def test_gallery_images_are_sent_as_media_groups(tmp_path):
    bot = AlbumBot()
    result = make_album(tmp_path, 12)
    progress = Progress()

    first = await gallery_uploader().send_gallery(
        bot, 1, result, progress, "https://insta/p/1"
    )

    assert first.message_id == 101
    assert [len(group) for group in bot.groups] == [10, 2]
    assert bot.documents == []
    caption = bot.groups[0][0].caption or ""
    assert caption.startswith("<b>Album</b>")
    assert all(item.caption is None for item in bot.groups[0][1:])
    assert progress.pct == 100.0


@pytest.mark.asyncio
async def test_gallery_document_mode_sends_every_file(tmp_path):
    bot = AlbumBot()
    result = make_album(tmp_path, 3)

    await gallery_uploader().send_gallery(
        bot, 1, result, Progress(), "", as_document=True
    )

    assert bot.groups == []
    assert len(bot.documents) == 3
    assert bot.documents[0]["caption"].startswith("<b>Album</b>")
    assert bot.documents[1]["caption"] == ""


@pytest.mark.asyncio
async def test_gallery_single_file_uses_normal_send(tmp_path):
    bot = AlbumBot()
    result = make_album(tmp_path, 1)

    await gallery_uploader().send_gallery(bot, 1, result, Progress(), "")

    assert bot.groups == []
    assert len(bot.photos) == 1


# ── ZIP برای لینک مستقیم ─────────────────────────────────────
def test_zip_parts_builds_single_archive(tmp_path):
    result = make_album(tmp_path, 3)

    zipped = JobManager._zip_parts(result)

    assert zipped.path.suffix == ".zip"
    assert zipped.path.is_file()
    assert zipped.mime == "application/zip"
    assert zipped.parts == [zipped.path]
    with zipfile.ZipFile(zipped.path) as zf:
        assert len(zf.namelist()) == 3


def test_custom_name_is_ignored_for_multi_part_gallery(tmp_path):
    result = make_album(tmp_path, 2)
    original = result.path

    assert apply_custom_name(result, "renamed") is result
    assert result.path == original


# ── تشخیص NSFW گالری ────────────────────────────────────────
def test_gallery_adult_category_is_nsfw(monkeypatch):
    from app.services.sites import SiteIndex

    index = SiteIndex()
    monkeypatch.setattr(SiteIndex, "match", lambda self, url: None)
    monkeypatch.setattr(gallery, "extractor_name", lambda url: "e621")

    assert index.is_nsfw_url("https://e621.net/posts/1") is True
    monkeypatch.setattr(gallery, "extractor_name", lambda url: "pinterest")
    assert index.is_nsfw_url("https://pinterest.com/pin/1") is False

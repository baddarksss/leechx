"""Play Store/APKPure variants, support delivery and admin latency guards."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from telegram.error import TelegramError

from app.bot.flows import start as start_flow
from app.services import apkstore
from app.services.admin_group import AdminGroup
from app.services.drafts import DraftStore
from app.services.filestore import FileStore
from app.services.runtime_settings import RuntimeSettings

MB = 1024 * 1024

# ساختار واقعی صفحهٔ دانلود APKPure (فقط بلوک‌های لازم نگه داشته شده‌اند).
APKPURE_HTML = """
<html><head><title>Download WhatsApp Latest Version 2.26.42.74 Android APK</title></head>
<body>
<h1 class="title">WhatsApp</h1>
<div class="apk-variants">
  <div class="group-title"><svg></svg>armeabi-v7a</div>
  <div class="apk" data-dt-app="com.whatsapp">
    <div class="info"><div class="info-top">
      <span class="name one-line">2.26.42.74</span>
      <span class="code one-line">(264207400)</span>
      <span class="tag one-line" data-tag="XAPK">XAPK</span>
    </div><div class="info-bottom one-line">
      <span class="size">95.7 MB</span><span class="sdk">Android 6.0+</span>
    </div></div>
    <a class="download-btn" href="https://d.apkpure.com/b/XAPK/com.whatsapp?versionCode=264207400&amp;nc=armeabi-v7a&amp;sv=23">
  </div>
  <div class="group-title"><svg></svg>arm64-v8a</div>
  <div class="apk" data-dt-app="com.whatsapp">
    <div class="info"><div class="info-top">
      <span class="name one-line">2.26.42.74</span>
      <span class="code one-line">(264207400)</span>
      <span class="tag one-line" data-tag="XAPK">XAPK</span>
    </div><div class="info-bottom one-line">
      <span class="size">150.5 MB</span><span class="sdk">Android 6.0+</span>
    </div></div>
    <a class="download-btn" href="https://d.apkpure.com/b/XAPK/com.whatsapp?versionCode=264207400&amp;nc=arm64-v8a&amp;sv=23">
  </div>
  <div class="group-title"><svg></svg>universal</div>
  <div class="apk" data-dt-app="com.whatsapp">
    <div class="info"><div class="info-top">
      <span class="name one-line">2.26.42.74</span>
      <span class="tag one-line" data-tag="APK">APK</span>
    </div><div class="info-bottom one-line"><span class="size">80.0 MB</span></div></div>
    <a class="download-btn" href="https://d.apkpure.com/b/APK/com.whatsapp?versionCode=264207400&amp;nc=universal&amp;sv=23">
  </div>
  <div class="group-title"><svg></svg>arm64-v8a</div>
  <div class="apk" data-dt-app="com.other.app">
    <div class="info"><div class="info-top"><span class="name one-line">9.9</span>
      <span class="tag one-line" data-tag="APK">APK</span></div>
      <div class="info-bottom one-line"><span class="size">1.0 MB</span></div></div>
    <a class="download-btn" href="https://d.apkpure.com/b/APK/com.other.app?versionCode=1">
  </div>
</div>
</body></html>
"""


@pytest.fixture(autouse=True)
def _clean_apk_cache():
    apkstore.reset_cache()
    yield
    apkstore.reset_cache()


def test_package_detection():
    assert apkstore.package_of(
        "https://play.google.com/store/apps/details?id=com.whatsapp&hl=fa"
    ) == "com.whatsapp"
    assert apkstore.package_of("market://details?id=org.telegram.messenger") == (
        "org.telegram.messenger"
    )
    assert apkstore.package_of(
        "https://apkpure.com/whatsapp-android/com.whatsapp/download"
    ) == "com.whatsapp"
    assert apkstore.package_of("https://example.com/watch?v=1") is None
    assert apkstore.package_of("https://play.google.com/store/movies") is None
    assert apkstore.is_apk_media(
        "https://d.apkpure.com/b/XAPK/com.whatsapp?versionCode=1"
    )


def test_parse_page_keeps_only_this_app_and_orders_arm64_first():
    page = apkstore.parse_page(
        APKPURE_HTML,
        "com.whatsapp",
        "https://apkpure.com/whatsapp-android/com.whatsapp/download",
    )
    assert page is not None
    assert page.title == "WhatsApp"
    assert page.version == "2.26.42.74"
    assert [link.abi for link in page.links] == [
        "arm64-v8a",
        "armeabi-v7a",
        "universal",
    ]
    assert [link.ext for link in page.links] == ["xapk", "xapk", "apk"]
    assert page.links[0].size == int(150.5 * MB)
    assert page.links[1].size == int(95.7 * MB)
    assert all("com.whatsapp" in link.url for link in page.links)

    options = apkstore.options_for(page)
    assert [opt.code for opt in options] == ["arm64-v8a", "armeabi-v7a", "universal"]
    assert all(opt.kind == "video" for opt in options)
    assert all(opt.codec == "apk" for opt in options)
    assert options[0].media_url.startswith("https://d.apkpure.com/")
    assert "arm64-v8a" in options[0].label and "MB" in options[0].label
    assert options[0].ext == "xapk"


def test_parse_size_and_media_package_fallback():
    assert apkstore.parse_size("150.5 MB") == int(150.5 * MB)
    assert apkstore.parse_size("—") is None
    url = "https://d.apkpure.com/b/XAPK/Y29tLndoYXRzYXBwXzI2NDIwNzQwMF82YmI5ODJmZQ"
    assert apkstore.package_from_media(url) == "com.whatsapp"


def test_combined_abi_group_becomes_universal():
    html = """
    <body><h1 class="title">F-Droid</h1>
    <div class="group-title"><svg></svg>arm64-v8a, armeabi-v7a, x86, x86_64</div>
    <div class="apk" data-dt-app="org.fdroid.fdroid">
      <div class="info"><div class="info-top"><span class="name one-line">1.19.1</span></div>
      <div class="info-bottom one-line"><span class="size">12.4 MB</span></div></div>
      <a class="download-btn" href="https://d.apkpure.com/b/APK/org.fdroid.fdroid?versionCode=1019001"></a>
    </div></body>
    """
    page = apkstore.parse_page(
        html, "org.fdroid.fdroid", "https://apkpure.com/fdroid/org.fdroid.fdroid/download"
    )
    assert page is not None
    assert page.links[0].abi == "universal"
    assert apkstore.options_for(page)[0].label.startswith("universal")


def test_remembered_page_registers_cdn_session():
    page = apkstore.parse_page(APKPURE_HTML, "com.whatsapp", "https://apkpure.com/x")
    page.cookie = "cf_clearance=abc"
    page.user_agent = "UA/1"
    apkstore._remember_page(page)
    session = apkstore.session_for(page.links[0].url)
    assert session is not None
    assert session.cookie == "cf_clearance=abc"
    assert session.user_agent == "UA/1"
    assert session.referer == "https://apkpure.com/x"


# ── جریان لینک ────────────────────────────────────────────────
class FakeMessage:
    def __init__(self, text: str = "") -> None:
        self.texts: list[str] = []
        self.kwargs: list[dict] = []
        self.chat_id = 1
        self.message_id = 10
        self.text = text
        self.deleted = False

    async def reply_text(self, text, **kwargs):
        self.texts.append(text)
        self.kwargs.append(kwargs)
        return self

    async def edit_text(self, text, **kwargs):
        self.texts.append(text)
        self.kwargs.append(kwargs)

    async def delete(self):
        self.deleted = True


class FakeJobs:
    def __init__(self) -> None:
        self.tasks: list = []

    async def submit(self, task) -> int:
        self.tasks.append(task)
        return 1


def make_context(hub=None, uses_local_api: bool = False):
    jobs = FakeJobs()
    services = SimpleNamespace(
        cfg=SimpleNamespace(
            per_user_concurrency=1,
            max_height=0,
            uses_local_api=uses_local_api,
            owners=[1],
        ),
        settings=SimpleNamespace(
            daily_quota=0,
            nsfw_enabled=True,
            ttl_hours=6.0,
            max_links_per_user=0,
            max_upload_bytes=2000 * MB,
        ),
        limiter=SimpleNamespace(has_slot=lambda *_: True, hit=lambda *_: 0),
        sites=SimpleNamespace(is_nsfw_url=lambda url: False),
        drafts=DraftStore(),
        jobs=jobs,
        admin_group=hub,
    )
    context = SimpleNamespace(user_data={"lang": "fa"}, bot_data={"services": services}, bot=None)
    return context, services, jobs


def make_update(message: FakeMessage | None = None):
    message = message or FakeMessage()
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=1, username="u", first_name="U", is_bot=False),
        effective_chat=SimpleNamespace(id=1, type="private"),
        effective_message=message,
        callback_query=None,
    )


@pytest.mark.asyncio
async def test_play_link_shows_apk_variants(monkeypatch, db):
    from app.bot.flows import link as link_flow

    page = apkstore.parse_page(APKPURE_HTML, "com.whatsapp", "https://apkpure.com/x")
    page.cookie = "cf_clearance=abc"

    async def fake_fetch(cfg, url, force=False):
        return page

    monkeypatch.setattr(apkstore, "fetch_page", fake_fetch)
    update = make_update()
    context, services, jobs = make_context()

    await link_flow.handle_link(
        update, context, "https://play.google.com/store/apps/details?id=com.whatsapp"
    )

    assert jobs.tasks == []
    draft = next(iter(services.drafts._items.values()))
    assert draft.kind == "apk"
    assert draft.title == "WhatsApp"
    assert [opt.code for opt in draft.options] == [
        "arm64-v8a",
        "armeabi-v7a",
        "universal",
    ]
    body = update.effective_message.texts[-1]
    assert "WhatsApp" in body and "com.whatsapp" in body
    buttons = update.effective_message.kwargs[-1]["reply_markup"]
    labels = [button.text for row in buttons.inline_keyboard for button in row]
    assert any("arm64-v8a" in label and "MB" in label for label in labels)


@pytest.mark.asyncio
async def test_large_apk_switches_to_direct_link(monkeypatch, db):
    from app.bot.flows import callbacks as callbacks_flow
    from app.bot.flows import link as link_flow

    page = apkstore.parse_page(APKPURE_HTML, "com.whatsapp", "https://apkpure.com/x")

    async def fake_fetch(cfg, url, force=False):
        return page

    monkeypatch.setattr(apkstore, "fetch_page", fake_fetch)
    update = make_update()
    context, services, _jobs = make_context()
    await link_flow.handle_link(
        update, context, "https://play.google.com/store/apps/details?id=com.whatsapp"
    )

    draft = next(iter(services.drafts._items.values()))
    big = next(opt for opt in draft.options if opt.code == "arm64-v8a")
    query = SimpleNamespace(
        message=update.effective_message,
        answers=[],
    )

    async def answer(text=None, show_alert=False):
        query.answers.append(text)

    query.answer = answer
    update.callback_query = query
    await callbacks_flow._on_quality(update, context, [draft.id, big.code, "v"])

    assert draft.option is big
    assert draft.destination == "link"
    assert draft.send_as == "document"
    assert query.answers and "لینک مستقیم" in str(query.answers[0])


# ── پیام پشتیبانی ────────────────────────────────────────────
class ReportBot:
    def __init__(self, group_fails: bool = True) -> None:
        self.group_fails = group_fails
        self.sent: list[tuple[int, str, dict]] = []

    async def create_forum_topic(self, chat_id, name):
        return SimpleNamespace(message_thread_id=len(self.sent) + 100)

    async def send_message(self, chat_id, text, **kwargs):
        if self.group_fails and chat_id < 0:
            raise TelegramError("group is unavailable")
        self.sent.append((chat_id, text, kwargs))
        return SimpleNamespace(message_id=len(self.sent))


@pytest.mark.asyncio
async def test_report_falls_back_to_owner_direct_message(db):
    settings = RuntimeSettings(db)
    await settings.load()
    hub = AdminGroup(db, settings)
    bot = ReportBot(group_fails=True)
    hub.attach(bot)
    await hub.configure(-100123456789, "ops")
    report = SimpleNamespace(
        kind="contact", user_id=42, username="u", first_name="U",
        url="", text="please help", id=7,
    )
    assert await hub.notify_report(report) is True
    assert bot.sent and bot.sent[-1][0] == 1
    assert "please help" in bot.sent[-1][1]


@pytest.mark.asyncio
async def test_contact_confirmation_is_a_new_message(db):
    delivered = []

    class Hub:
        async def notify_report(self, report):
            delivered.append(report)
            return True

    update = make_update(FakeMessage("سلام"))
    context, _services, _jobs = make_context(hub=Hub())
    await start_flow.handle_contact(update, context)

    message = update.effective_message
    assert delivered and delivered[0].kind == "contact"
    assert message.texts and "ادمین" in message.texts[-1]
    assert message.deleted is True


@pytest.mark.asyncio
async def test_file_size_cache_avoids_repeated_walk(tmp_path):
    store = FileStore(tmp_path / "files", tmp_path / "tmp")
    (store.jobs / "a").mkdir()
    (store.jobs / "a" / "f.bin").write_bytes(b"x" * 100)
    first = store.total_size()
    assert first == 100
    (store.jobs / "a" / "f2.bin").write_bytes(b"y" * 50)
    assert store.total_size() == first  # کش کوتاه‌عمر
    store.invalidate_size_cache()
    assert store.total_size() == 150

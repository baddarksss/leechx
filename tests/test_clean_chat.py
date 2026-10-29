"""v5.3: پنل تک‌پیامی، پاسخ فوری دکمه‌ها و توکن عیب‌یابی با یک آدرس کامل."""
from __future__ import annotations

import time
from types import SimpleNamespace

import pytest
from aiohttp.test_utils import TestClient, TestServer
from telegram import InlineKeyboardMarkup, ReplyKeyboardMarkup

from app.bot import common
from app.bot import keyboards as kb
from app.bot.flows.text_router import _admin_section_for_label
from app.core import text

from .test_deploy_debug import make_debug


# ── کیبورد عیب‌یابی ─────────────────────────────────────────
def _token(token_id: int, scopes: str = "read"):
    return SimpleNamespace(id=token_id, scopes=scopes, expires_at=int(time.time()) + 3600, uses=0)


def test_debug_menu_has_no_duplicate_buttons_and_trash_per_token():
    menu = kb.debug_menu("fa", [_token(1), _token(2, "read,write")], True, 24, ttl=6)
    labels = [button.text for row in menu.inline_keyboard for button in row if button.text != "🗑"]
    assert len(labels) == len(set(labels)), labels
    callbacks = [button.callback_data for row in menu.inline_keyboard for button in row]
    assert callbacks[0] == "a|dbtoggle"
    assert "a|dbmake|read|6" in callbacks
    assert "a|dbmake|read|24" not in callbacks  # مدت با دکمهٔ چرخشی انتخاب می‌شود
    for token_id in (1, 2):
        row = next(r for r in menu.inline_keyboard if r[0].callback_data == f"a|dbinfo|{token_id}")
        assert row[-1].text == "🗑"
        assert row[-1].callback_data == f"a|dbrevoke|{token_id}"
    assert sum(1 for c in callbacks if c == "a|preview") == 1


def test_debug_ttl_cycles_within_cap():
    assert kb.next_debug_ttl(1, 24) == 6
    assert kb.next_debug_ttl(6, 24) == 24
    assert kb.next_debug_ttl(24, 24) == 1
    assert kb.next_debug_ttl(6, 6) == 1


def test_token_menu_copies_the_full_url():
    url = "https://bot.example.com/debug/k/lxdbg_abc"
    menu = kb.debug_token_menu("fa", url, 7)
    copy = menu.inline_keyboard[0][0]
    assert copy.copy_text.text == url
    callbacks = [b.callback_data for row in menu.inline_keyboard for b in row if b.callback_data]
    assert "a|dbrevoke|7" in callbacks


# ── آدرس تک‌تکهٔ توکن ───────────────────────────────────────
@pytest.mark.asyncio
async def test_single_url_token_reads_and_lists_endpoints(db, tmp_path):
    debug, settings, _updater, application = await make_debug(db, tmp_path)
    await settings.set("public_base_url", "https://bot.example.com")
    raw, _row = await debug.create(1, hours=1, scopes="read")
    url = debug.access_url("https://bot.example.com/", raw)
    assert url == f"https://bot.example.com/debug/k/{raw}"

    async with TestClient(TestServer(application)) as client:
        index = await client.get(f"/debug/k/{raw}")
        assert index.status == 200
        payload = await index.json()
        assert payload["endpoints"]["health"]["url"] == f"{url}/health"
        assert "source_write" not in payload["endpoints"]  # read-only token

        assert (await client.get(f"/debug/k/{raw}/health")).status == 200
        source = await client.get(f"/debug/k/{raw}/source?path=app/version.py")
        assert source.status == 200
        denied = await client.post(f"/debug/k/{raw}/source", json={"path": "app/x.py", "content": "X=1"})
        assert denied.status == 403
        assert (await client.get("/debug/k/lxdbg_wrong/health")).status == 401


# ── پاسخ callback و ویرایش ─────────────────────────────────
@pytest.mark.asyncio
async def test_safe_answer_is_idempotent_and_plain_text():
    calls = []

    async def answer(body=None, show_alert=False):
        calls.append(body)

    query = SimpleNamespace(id=f"q-{time.time_ns()}", answer=answer)
    assert await common.safe_answer(query, "🗑 حذف شد: <b>x</b>") is True
    assert await common.safe_answer(query, "second") is False
    assert calls == ["🗑 حذف شد: x"]


@pytest.mark.asyncio
async def test_edit_drops_reply_keyboard_instead_of_failing():
    seen = {}

    class Message:
        async def edit_text(self, body, **kwargs):
            seen.update(kwargs)

    message = Message()
    markup = ReplyKeyboardMarkup([["a"]])
    assert await common.edit(message, "body", reply_markup=markup) is message
    assert "reply_markup" not in seen


# ── پنل تک‌پیامی ────────────────────────────────────────────
class _Bot:
    def __init__(self):
        self.edited = []
        self.deleted = []

    async def edit_message_text(self, body, chat_id=None, message_id=None, **kwargs):
        self.edited.append((chat_id, message_id, body))
        return None

    async def delete_message(self, chat_id, message_id):
        self.deleted.append((chat_id, message_id))


class _Msg:
    def __init__(self, message_id: int, chat_id: int = 5):
        self.message_id = message_id
        self.chat_id = chat_id
        self.sent = []
        self.deleted = False

    async def reply_text(self, body, **kwargs):
        reply = _Msg(self.message_id + 1, self.chat_id)
        self.sent.append((body, kwargs))
        return reply

    async def delete(self):
        self.deleted = True


def _text_update(message_id: int):
    return SimpleNamespace(
        callback_query=None,
        effective_chat=SimpleNamespace(id=5, type="private"),
        effective_message=_Msg(message_id),
    )


@pytest.mark.asyncio
async def test_panel_edits_previous_menu_when_it_is_the_last_message():
    bot = _Bot()
    context = SimpleNamespace(user_data={}, bot=bot)

    first = _text_update(10)
    await common.panel(first, context, "one", InlineKeyboardMarkup([]))
    await common.drop_user_input(first)
    assert first.effective_message.deleted is True
    assert context.user_data[common.PANEL_KEY]["id"] == 11

    # ضربهٔ بعدی (12) درست بعد از پنل (11) است → همان پنل ویرایش می‌شود.
    second = _text_update(12)
    await common.panel(second, context, "two")
    assert bot.edited == [(5, 11, "two")]
    assert second.effective_message.sent == []

    # پیام دیگری بین‌شان آمد (14) → پنل تازه پایین و پنل قبلی پاک می‌شود.
    third = _text_update(15)
    await common.panel(third, context, "three")
    assert third.effective_message.sent
    assert (5, 11) in bot.deleted
    assert context.user_data[common.PANEL_KEY]["id"] == 16


@pytest.mark.parametrize("language", text.LANG_ORDER)
def test_admin_cancel_shortcut_is_removed_but_legacy_keyboard_still_routes(language):
    assert "cancel" not in kb.persistent_admin_labels(language)
    assert text.t(language, "sec_cancel") not in kb.persistent_admin_labels(language).values()
    assert _admin_section_for_label(text.t(language, "sec_cancel")) == kb.SEC_CANCEL

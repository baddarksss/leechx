"""تشخیص آهنگ (Shazam): پارس خروجی، عبارت جستوجو، و دکمهٔ «آهنگ کامل»."""
from __future__ import annotations

import pytest

from app.bot.flows import callbacks as callbacks_flow
from app.bot.flows import link as link_flow
from app.bot.keyboards import delivery_menu
from app.core import text
from app.services.downloader import MediaInfo, parse_shazam_match, song_query
from app.services.drafts import Draft
from app.services.formats import FormatOption
from tests.test_flows import VIDEO_FORMATS, FakeQuery, make_context, make_update


def test_parse_shazam_match_track_and_matches():
    assert parse_shazam_match({"track": {"title": "Song", "subtitle": "Artist"}}) == (
        "Artist", "Song"
    )
    assert parse_shazam_match({"matches": [{"title": "S", "subtitle": "A"}]}) == ("A", "S")
    assert parse_shazam_match({"matches": []}) is None
    assert parse_shazam_match({"track": {}}) is None
    assert parse_shazam_match(None) is None


def test_song_query_helper():
    assert song_query("Queen", "Bohemian Rhapsody") == "Queen Bohemian Rhapsody"
    assert song_query("", "Solo") == "Solo"


def _callbacks(draft: Draft) -> list[str]:
    return [
        b.callback_data
        for row in delivery_menu("fa", draft).inline_keyboard
        for b in row
    ]


def test_song_button_only_for_ytdlp_links():
    option = FormatOption(kind="video", code="720", label="720p", selector="720", ext="mp4")
    yt = Draft(id="a", user_id=1, chat_id=1, url="https://youtube.com/watch?v=x",
               title="v", kind="link", option=option, extractor="Youtube")
    kvs = Draft(id="b", user_id=1, chat_id=1, url="https://tube/x",
                title="v", kind="link", option=option, extractor="KVS")
    hls = Draft(id="c", user_id=1, chat_id=1, url="https://voe/x",
                title="v", kind="link", option=option, extractor="HLS")
    direct = Draft(id="d", user_id=1, chat_id=1, url="https://x.mp4",
                   title="v", kind="direct", option=option, extractor="")

    assert any(c and c.endswith("|song") for c in _callbacks(yt))
    assert not any(c and c.endswith("|song") for c in _callbacks(kvs))
    assert not any(c and c.endswith("|song") for c in _callbacks(hls))
    assert not any(c and c.endswith("|song") for c in _callbacks(direct))


@pytest.mark.asyncio
async def test_song_button_enqueues_song_job(db):
    url = "https://www.instagram.com/reel/SONG2/"
    info = MediaInfo(url=url, title="Reel", extractor="Instagram", formats=VIDEO_FORMATS)
    ctx, svc, jobs = make_context(info)
    request = make_update()
    await link_flow.handle_link(request, ctx, url)
    draft = next(iter(svc.drafts._items.values()))

    buttons = [b for row in request.effective_message.kwargs[-1]["reply_markup"].inline_keyboard for b in row]
    assert any(b.callback_data and b.callback_data.endswith("|song") for b in buttons)

    await callbacks_flow._on_delivery(
        make_update(FakeQuery(request.effective_message)), ctx, [draft.id, "song"]
    )
    assert len(jobs.tasks) == 1
    assert jobs.tasks[0].mode == "song"
    assert jobs.tasks[0].option.kind == "audio"
    assert jobs.tasks[0].option.code == "song"
    assert not len(svc.drafts)


def test_delivery_text_marks_audio_mode():
    option = FormatOption(
        kind="audio", code="mp3", label="MP3 192k",
        selector="ba[ext=m4a]/ba/b", ext="mp3",
    )
    draft = Draft(
        id="a", user_id=1, chat_id=1, url="https://x", title="T",
        kind="link", option=option, send_as="document",
    )
    body = link_flow.delivery_text("fa", draft, ttl_hours=4)
    assert text.t("fa", "delivery_mode_audio") in body

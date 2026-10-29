"""Instagram/TikTok skip quality, delivery choices explain what they do."""
from __future__ import annotations

import pytest

from app.bot.flows import callbacks as callbacks_flow
from app.bot.flows import link as link_flow
from app.bot.keyboards import delivery_menu
from app.core import text
from app.services.downloader import MediaInfo
from app.services.drafts import Draft
from app.services.formats import FormatOption
from tests.test_flows import VIDEO_FORMATS, FakeQuery, make_context, make_update


@pytest.mark.parametrize("url,extractor", [
    ("https://www.instagram.com/reel/EXAMPLE/", "Instagram"),
    ("https://instagram.com/p/EXAMPLE/", "Instagram"),
    ("https://www.instagram.com/stories/user/123/", "Instagram"),
    ("https://instagr.am/p/EXAMPLE/", "Instagram"),
    ("https://www.tiktok.com/@creator/video/123456", "TikTok"),
    ("https://vm.tiktok.com/ZM1234/", "TikTok"),
    ("https://vt.tiktok.com/123456/", "TikTok"),
    ("https://www.tiktok.com/t/123/", "TikTok"),
    ("https://shortener.example/redirect", "TikTok"),
    ("https://redirect.example/IG", "InstagramUser"),
])
@pytest.mark.asyncio
async def test_social_links_go_directly_to_delivery(url, extractor, db):
    info = MediaInfo(
        url=url, title="Social Video", formats=VIDEO_FORMATS,
        duration=19, extractor=extractor,
    )
    context, services, jobs = make_context(info)
    request = make_update()
    await link_flow.handle_link(request, context, url)
    draft = next(iter(services.drafts._items.values()))
    assert draft.auto_quality is True
    assert draft.kind == "link"
    assert draft.option is not None
    assert draft.option.code == "auto"
    assert draft.option.kind == "video"
    assert draft.option.selector == "bv*+ba/b"
    assert "بهترین کیفیت" in request.effective_message.texts[-1]
    assert text.t("fa", "delivery_mode_video") in request.effective_message.texts[-1]
    buttons = [b for row in request.effective_message.kwargs[-1]["reply_markup"].inline_keyboard for b in row]
    actions = {b.callback_data.rsplit("|", 1)[-1] for b in buttons if b.callback_data}
    assert {"video", "document", "telegram", "link", "r", "thumbnail", "start"} <= actions
    assert "q" not in actions
    assert all(not b.callback_data.startswith("q|") for b in buttons if b.callback_data)
    assert jobs.tasks == []  # Merely presenting options does not start transfer.


@pytest.mark.parametrize("url", [
    "https://tiktok.com.evil.example/@user/video/100",
    "https://notinstagram.com/reel/xyz",
    "https://youtube.com/watch?v=123456",
    "https://www.aparat.com/v/12345",
    "https://site.example/resource?url=instagram.com",
])
def test_lookalike_domains_not_auto_quality(url):
    assert not link_flow.auto_quality_for_social(url, "OtherSite")


@pytest.mark.asyncio
async def test_social_redirect_detected_by_extractor_or_final_url(db):
    info = MediaInfo(url="https://www.tiktok.com/@user/video/9", title="v",
                     extractor="Generic", formats=VIDEO_FORMATS)
    context, svc, _ = make_context(info)
    update = make_update()
    await link_flow.handle_link(update, context, "https://short.example/video")
    draft = next(iter(svc.drafts._items.values()))
    assert draft.auto_quality


@pytest.mark.parametrize("action,mode", [
    ("v", "video"), ("d", "document"), ("l", "link"),
])
@pytest.mark.asyncio
async def test_social_delivery_modes_still_enqueue(action, mode, db):
    url="https://www.instagram.com/reel/REEL/"
    info=MediaInfo(url=url,title="My Reel",extractor="Instagram",formats=VIDEO_FORMATS)
    ctx, svc, jobs=make_context(info)
    request=make_update()
    await link_flow.handle_link(request,ctx,url)
    draft=next(iter(svc.drafts._items.values()))
    cb=make_update(FakeQuery(request.effective_message))
    await callbacks_flow._on_delivery(cb,ctx,[draft.id,action])
    assert len(jobs.tasks)==1
    assert jobs.tasks[0].mode==mode
    assert jobs.tasks[0].option.selector=="bv*+ba/b"
    assert not len(svc.drafts)


@pytest.mark.asyncio
async def test_social_rename_still_works(db):
    url="https://www.tiktok.com/@maker/video/123"
    info=MediaInfo(url=url,title="Great Clip",extractor="TikTok",formats=VIDEO_FORMATS)
    ctx,svc,_=make_context(info)
    request=make_update()
    await link_flow.handle_link(request,ctx,url)
    draft=next(iter(svc.drafts._items.values()))
    await callbacks_flow._on_delivery(make_update(FakeQuery(request.effective_message)),ctx,[draft.id,"r"])
    assert ctx.user_data.get("state")=="rename"
    assert draft.auto_quality


@pytest.mark.asyncio
async def test_social_cannot_be_switched_to_manual_quality(db):
    url="https://www.instagram.com/reel/ID"
    info=MediaInfo(url=url,title="Video",extractor="Instagram",formats=VIDEO_FORMATS)
    ctx,svc,_=make_context(info)
    request=make_update()
    await link_flow.handle_link(request,ctx,url)
    draft=next(iter(svc.drafts._items.values()))
    await callbacks_flow._on_delivery(make_update(FakeQuery(request.effective_message)),ctx,[draft.id,"q"])
    assert draft.option is not None
    assert draft.option.code=="auto"


@pytest.mark.asyncio
async def test_youtube_still_offers_manual_quality(db):
    url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
    info = MediaInfo(url=url,title="Me at the zoo",extractor="Youtube",formats=VIDEO_FORMATS)
    ctx,svc,_=make_context(info)
    request=make_update()
    await link_flow.handle_link(request,ctx,url)
    draft=next(iter(svc.drafts._items.values()))
    assert not draft.auto_quality
    assert draft.option is None
    buttons=[b for row in request.effective_message.kwargs[-1]["reply_markup"].inline_keyboard for b in row]
    assert any(b.callback_data.startswith("q|") for b in buttons if b.callback_data)


@pytest.mark.parametrize("language", ["fa", "en", "ru"])
def test_delivery_copy_is_compact_localized_and_reflects_selected_destination(language):
    draft = Draft(
        id="abc",
        user_id=1,
        chat_id=1,
        url="https://example.com/clip.mp4",
        title="Demo",
        kind="direct",
        option=FormatOption(
            kind="direct", code="direct", label="direct", selector="", ext="mp4"
        ),
        custom_thumbnail=b"thumb",
        destination="link",
    )
    rendered = link_flow.delivery_text(language, draft, ttl_hours=4.5)
    markup = delivery_menu(language, draft)
    buttons = [b for row in markup.inline_keyboard for b in row]

    assert "Demo" in rendered
    assert "4.5" in rendered
    assert len(rendered.splitlines()) <= 4
    assert "<code>" not in rendered
    assert text.t(language, "delivery_ttl_short", ttl="4.5") in rendered
    assert any(b.callback_data == "o|abc|destination|telegram" for b in buttons)
    assert any(b.callback_data == "o|abc|destination|link" for b in buttons)
    assert any(b.callback_data == "o|abc|tab|format" for b in buttons)
    assert any(b.callback_data == "o|abc|tab|destination" for b in buttons)
    assert any(b.callback_data == "o|abc|tab|edits" for b in buttons)
    assert buttons[-1].text == text.t(language, "deliver_start_link_btn")
    assert buttons[-1].style == "success"
    header_callbacks = {
        "o|abc|tab|format",
        "o|abc|tab|destination",
        "o|abc|tab|edits",
    }
    assert all(
        button.style == "primary" for button in buttons
        if button.callback_data in header_callbacks
    )
    assert all(
        button.style is None for button in buttons
        if button.callback_data not in header_callbacks and button is not buttons[-1]
    )
    assert all("⬇️" in text.t(language, key) for key in (
        "delivery_tab_format", "delivery_tab_destination", "delivery_tab_edits"
    ))
    assert all("🟦" not in button.text and "🟪" not in button.text for button in buttons)
    assert text.t("fa", "deliver_thumbnail_btn") == "🖼 تامبنیل"


def test_manual_quality_back_and_file_actions_are_unstyled():
    option = FormatOption(kind="video", code="720", label="720p", selector="720", ext="mp4")
    draft = Draft(
        id="manual",
        user_id=1,
        chat_id=1,
        url="https://youtube.com/watch?v=x",
        title="Video",
        kind="link",
        option=option,
    )
    buttons = [button for row in delivery_menu("fa", draft).inline_keyboard for button in row]
    by_data = {button.callback_data: button for button in buttons}

    assert by_data["o|manual|tab|format"].style == "primary"
    assert by_data["o|manual|tab|destination"].style == "primary"
    assert by_data["o|manual|tab|edits"].style == "primary"
    assert by_data["o|manual|q"].style is None
    assert by_data["o|manual|thumbnail"].style is None
    assert by_data["o|manual|r"].style is None
    assert by_data["o|manual|start"].style == "success"
    assert all(
        button.style is None
        for button in buttons
        if button.callback_data not in {
            "o|manual|tab|format",
            "o|manual|tab|destination",
            "o|manual|tab|edits",
            "o|manual|start",
        }
    )


def test_auto_social_delivery_has_no_quality_back_but_youtube_does():
    format_option=FormatOption(kind="video",code="auto",label="Best",
                               selector="bv*+ba/b",ext="mp4")
    social=Draft(id="s1",user_id=1,chat_id=1,url="https://instagram.com",title="IG",
                 option=format_option,auto_quality=True)
    youtube=Draft(id="s2",user_id=1,chat_id=1,url="https://youtube.com",title="YT",
                  option=format_option,auto_quality=False)
    def keys(d):
        return [b.callback_data for row in delivery_menu("fa",d).inline_keyboard for b in row]
    assert "o|s1|q" not in keys(social)
    assert "o|s2|q" in keys(youtube)


@pytest.mark.asyncio
async def test_delivery_section_tab_only_explains_choices(db):
    info = MediaInfo(
        url="https://www.instagram.com/reel/ID",
        title="Video",
        extractor="Instagram",
        formats=VIDEO_FORMATS,
    )
    context, services, jobs = make_context(info)
    request = make_update()
    await link_flow.handle_link(request, context, info.url)
    draft = next(iter(services.drafts._items.values()))
    before = (draft.send_as, draft.destination, draft.option)
    query = FakeQuery(request.effective_message)

    await callbacks_flow._on_delivery(
        make_update(query), context, [draft.id, "tab", "format"]
    )

    assert query.answers[-1] == text.t("fa", "delivery_section_hint")
    assert (draft.send_as, draft.destination, draft.option) == before
    assert jobs.tasks == []

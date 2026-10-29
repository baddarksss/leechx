"""Instagram/TikTok skip quality, delivery choices explain what they do."""
from __future__ import annotations

import pytest

from app.bot.flows import link as link_flow, callbacks as callbacks_flow
from app.bot.keyboards import delivery_menu
from app.services.downloader import MediaInfo
from app.services.drafts import Draft
from app.services.formats import FormatOption
from tests.test_flows import (
    VIDEO_FORMATS, FakeQuery, make_context, make_update
)


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
async def test_social_links_go_directly_to_delivery(url, extractor):
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
    assert "چطور می‌خواهی فایل را دریافت کنی؟" in request.effective_message.texts[-1]
    buttons = [b for row in request.effective_message.kwargs[-1]["reply_markup"].inline_keyboard for b in row]
    actions = {b.callback_data.rsplit("|", 1)[-1] for b in buttons if b.callback_data}
    assert {"v", "d", "l", "r"} <= actions
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
async def test_social_redirect_detected_by_extractor_or_final_url():
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
async def test_social_delivery_modes_still_enqueue(action, mode):
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
async def test_social_rename_still_works():
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
async def test_social_cannot_be_switched_to_manual_quality():
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
async def test_youtube_still_offers_manual_quality():
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


@pytest.mark.parametrize("language", ["fa", "en"])
def test_delivery_copy_explains_every_option_and_ttl(language):
    draft=Draft(id="abc",user_id=1,chat_id=1,url="https://example.com/clip.mp4",title="Demo",
                kind="direct",option=FormatOption(kind="direct",code="direct",label="direct",
                                                   selector="",ext="mp4"))
    rendered=link_flow.delivery_text(language,draft,ttl_hours=4.5)
    buttons=[b.text for row in delivery_menu(language,draft).inline_keyboard for b in row]
    assert "Demo" in rendered
    assert "4.5" in rendered
    assert len([b for b in buttons if "🎬" in b])==1
    assert len([b for b in buttons if "📁" in b])==1
    assert len([b for b in buttons if "🔗" in b])==1
    assert "direct" not in rendered
    if language=="fa":
        assert "پخش" in rendered and "فشرده‌سازی" in rendered and "ساعت" in rendered
        assert "حجم" in rendered and "نامشخص" in rendered
        assert "دریافت" in rendered
    else:
        assert "playback" in rendered and "compression" in rendered
        assert "hours" in rendered and "Unknown" in rendered


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

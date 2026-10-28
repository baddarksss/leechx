import time

import pytest

from app.db import repo


@pytest.mark.asyncio
async def test_users_upsert_and_lookup(db):
    user = await repo.upsert_user(100, "Ali", "Ali A")
    assert user.id == 100
    assert user.lang == "fa"

    again = await repo.upsert_user(100, "Ali2", "Ali B", lang="en")
    assert again.username == "Ali2"
    assert again.lang == "en"
    assert await repo.count_users() == 1

    found = await repo.find_user_by_username("@ali2")
    assert found is not None and found.id == 100
    assert await repo.get_user(999) is None


@pytest.mark.asyncio
async def test_ban_and_lang(db):
    await repo.upsert_user(5, "u", "U")
    await repo.set_banned(5, True)
    assert (await repo.get_user(5)).is_banned is True
    await repo.set_lang(5, "en")
    assert (await repo.get_user(5)).lang == "en"
    await repo.bump_downloads(5)
    await repo.bump_downloads(5)
    assert (await repo.get_user(5)).downloads == 2


@pytest.mark.asyncio
async def test_admins(db):
    await repo.add_admin(7, added_by=1)
    await repo.add_admin(7, added_by=1)  # تکراری بی‌اثر
    assert await repo.is_db_admin(7) is True
    assert await repo.count_admins() == 1
    rows = await repo.list_admins()
    assert rows[0].user_id == 7
    assert await repo.remove_admin(7) is True
    assert await repo.remove_admin(7) is False
    assert await repo.is_db_admin(7) is False


@pytest.mark.asyncio
async def test_settings(db):
    assert await repo.get_setting("ttl") is None
    await repo.set_setting("ttl", "6")
    assert await repo.get_setting("ttl") == "6"
    await repo.set_setting("ttl", "12")
    assert await repo.get_setting("ttl") == "12"
    await repo.set_setting("maintenance", "1")
    assert (await repo.all_settings())["maintenance"] == "1"


@pytest.mark.asyncio
async def test_jobs_lifecycle(db):
    await repo.create_job("j1", 1, 1, "https://x.com/a", selector="bv", quality="720p")
    job = await repo.get_job("j1")
    assert job.status == "queued"

    await repo.update_job("j1", status="running", started_at=int(time.time()))
    assert (await repo.get_job("j1")).status == "running"

    await repo.update_job("j1", status="done", size=123)
    done = await repo.get_job("j1")
    assert done.status == "done" and done.size == 123

    await repo.create_job("j2", 1, 1, "https://x.com/b")
    await repo.update_job("j2", status="running")
    await repo.create_job("j3", 2, 2, "https://x.com/c")

    assert len(await repo.active_jobs()) == 2
    stale = await repo.fail_stale_jobs()
    assert stale == 2
    assert len(await repo.active_jobs()) == 0

    total, ok, failed = await repo.jobs_count_today()
    assert total == 3
    assert ok == 1
    assert failed >= 2

    recent = await repo.recent_jobs(2)
    assert len(recent) == 2


@pytest.mark.asyncio
async def test_shared_files(db):
    row = await repo.create_shared("f1", 1, "/tmp/a.mp4", "a.mp4", "video/mp4", 500, 3600)
    assert row.expires_at > time.time()

    got = await repo.get_shared("f1")
    assert got.id == "f1"
    await repo.touch_shared("f1")
    assert (await repo.get_shared("f1")).downloads == 1

    assert await repo.count_shared() == 1
    assert await repo.shared_total_size() == 500
    assert list(await repo.expired_shared(int(time.time()) + 7200))[0].id == "f1"
    assert len(await repo.expired_shared()) == 0

    await repo.delete_shared("f1")
    assert await repo.get_shared("f1") is None


@pytest.mark.asyncio
async def test_events(db):
    await repo.log_event(1, "download_done", 10)
    await repo.log_event(1, "download_done", 5)
    await repo.log_event(1, "link_created")
    stats = await repo.events_since(int(time.time()) - 60)
    assert stats["download_done"] == 15
    assert stats["link_created"] == 1
    assert await repo.purge_events(-1) == 3


@pytest.mark.asyncio
async def test_logs_and_reports(db):
    await repo.add_log("error", "job", "boom", 5)
    await repo.add_log("WARNING", "report", "weird site")
    logs = await repo.recent_logs(10)
    assert len(logs) == 2
    assert {row.level for row in logs} == {"ERROR", "WARNING"}
    assert {row.source for row in logs} == {"job", "report"}

    report = await repo.add_report(
        "unsupported", 5, username="u", first_name="U", text="bad url", url="https://x/a"
    )
    assert report.status == "open"
    assert await repo.count_open_reports() == 1
    opened = await repo.recent_reports()
    assert len(opened) == 1 and opened[0].url == "https://x/a"

    assert await repo.set_report_status(report.id) is True
    assert await repo.set_report_status(99999) is False
    assert await repo.count_open_reports() == 0
    assert len(await repo.recent_reports()) == 0
    assert len(await repo.recent_reports(status=None)) == 1

    assert await repo.clear_logs() == 2
    assert await repo.recent_logs() == []


@pytest.mark.asyncio
async def test_stats_helpers(db):
    await repo.upsert_user(1, "a", "A")
    await repo.upsert_user(2, "b", "B")
    await repo.set_banned(2, True)
    assert await repo.count_users() == 2
    assert await repo.count_banned_users() == 1
    assert await repo.count_active_users(7) == 2

    await repo.create_shared("s1", 1, "/tmp/a", "a", "video/mp4", 10, 3600)
    await repo.create_shared("s2", 1, "/tmp/b", "b", "video/mp4", 10, -1)
    assert await repo.count_active_shared() == 1

    await repo.create_job("j1", 1, 1, "https://x/a")
    await repo.create_job("j2", 2, 2, "https://x/b")
    await repo.update_job("j2", status="running")
    await repo.create_job("j3", 1, 1, "https://x/c")
    await repo.update_job("j3", status="done")
    assert await repo.count_active_job_users() == 2


@pytest.mark.asyncio
async def test_claim_owner_is_first_come(db):
    owner, claimed = await repo.claim_owner(10)
    assert owner == 10 and claimed is True
    owner, claimed = await repo.claim_owner(20)
    assert owner == 10 and claimed is False
    assert await repo.get_setting("owner_id") == "10"


@pytest.mark.asyncio
async def test_user_events_since_is_per_user(db):
    await repo.log_event(1, "download_done", 2)
    await repo.log_event(1, "download_done", 3)
    await repo.log_event(2, "download_done", 10)
    await repo.log_event(1, "link_created", 99)
    since = int(time.time()) - 60
    assert await repo.user_events_since(1, "download_done", since) == 5
    assert await repo.user_events_since(2, "download_done", since) == 10
    assert await repo.user_events_since(3, "download_done", since) == 0
    assert await repo.user_events_since(1, "unknown", since) == 0

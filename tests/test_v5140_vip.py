"""v5.14.0: VIP users — limit exemption without admin rights."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.bot import guards
from app.db import repo


def test_unlimited_requires_admin_or_vip():
    plain = SimpleNamespace(user_data={"is_admin": False, "is_vip": False})
    vip = SimpleNamespace(user_data={"is_admin": False, "is_vip": True})
    admin = SimpleNamespace(user_data={"is_admin": True})
    preview_admin = SimpleNamespace(user_data={"is_admin": True, "preview": True})

    assert guards.unlimited(plain) is False
    assert guards.unlimited(vip) is True
    assert guards.unlimited(admin) is True
    # admin in preview behaves like a normal user
    assert guards.unlimited(preview_admin) is False
    # VIP never becomes an admin
    assert guards.current_admin(vip) is False
    assert guards.is_vip(vip) is True


@pytest.mark.asyncio
async def test_vip_flag_roundtrip_and_listing(db):
    await repo.set_vip(7001, True)
    row = await repo.get_user(7001)
    assert row is not None and row.vip is True
    assert await repo.count_vips() == 1
    listed = await repo.list_vips(10, 0)
    assert [item.id for item in listed] == [7001]
    await repo.set_vip(7001, False)
    row = await repo.get_user(7001)
    assert row is not None and row.vip is False
    assert await repo.count_vips() == 0
    assert await repo.list_vips(10, 0) == []

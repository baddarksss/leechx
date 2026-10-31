"""تقسیم فایل‌های بزرگ‌تر از سقف آپلود تلگرام."""
from __future__ import annotations

import pytest

from app.core import errors
from app.services import splitter


def test_planned_parts_and_usable_bytes():
    assert splitter.usable_bytes(1000) == 900
    assert splitter.planned_parts(0, 900) == 1
    assert splitter.planned_parts(900, 900) == 1
    assert splitter.planned_parts(901, 900) == 2
    assert splitter.planned_parts(2700, 900) == 3


def test_part_name_is_safe_and_numbered():
    assert splitter.part_name("movie:clip", 2, 3, ".mp4").endswith("(part 2 of 3).mp4")
    assert splitter.part_name("archive", 1, 4, ".zip", bytes_mode=True).endswith(
        ".part1.zip"
    )
    assert splitter.part_name("", 1, 2, ".bin")


@pytest.mark.asyncio
async def test_byte_split_is_lossless_and_under_the_cap(tmp_path):
    payload = bytes(range(256)) * 4096  # ۱ مگابایت
    source = tmp_path / "archive.bin"
    source.write_bytes(payload)
    limit = 400_000
    cap = splitter.usable_bytes(limit)

    plan = await splitter.split_file(source, limit, tmp_path)

    assert plan.method == "bytes"
    assert plan.count == splitter.planned_parts(len(payload), cap) == 3
    assert all(p.stat().st_size <= cap for p in plan.parts)
    assert sum(p.stat().st_size for p in plan.parts) == len(payload)
    assert b"".join(p.read_bytes() for p in plan.parts) == payload
    assert all(".part" in p.name for p in plan.parts)


@pytest.mark.asyncio
async def test_file_below_the_limit_is_not_split(tmp_path):
    source = tmp_path / "small.bin"
    source.write_bytes(b"x" * 500)

    plan = await splitter.split_file(source, 10_000, tmp_path)

    assert plan.method == "none"
    assert plan.count == 1
    assert plan.parts == [source]


@pytest.mark.asyncio
async def test_too_many_parts_is_rejected(tmp_path):
    source = tmp_path / "huge.bin"
    source.write_bytes(b"x" * 20_000)

    with pytest.raises(errors.SplitTooMany):
        await splitter.split_file(source, 1_000, tmp_path)

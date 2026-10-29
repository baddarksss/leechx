"""نسخهٔ LeechX — تنها منبع حقیقت نسخه.

قانون پروژه: هر تغییری در سورس باید این فایل، ``pyproject.toml`` و
``CHANGELOG.md`` را با هم به‌روز کند. تست ``tests/test_version.py`` همین
هم‌خوانی را تضمین می‌کند تا هیچ‌وقت نسخهٔ اشتباه به کاربر نشان داده نشود.

شماره‌گذاری: Semantic Versioning
    MAJOR  تغییر ناسازگار / بازطراحی بزرگ
    MINOR  قابلیت جدید سازگار
    PATCH  رفع باگ و بهبود کوچک
"""
from __future__ import annotations

import re

__version__ = "5.4.3"
CODENAME = "Localized Flow"
RELEASE_DATE = "2026-10-29"

# نسخهٔ حداقلی پایتون برای اجرای این سورس.
MIN_PYTHON = (3, 11)

_SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def parse_version(raw: str) -> tuple[int, int, int] | None:
    """تبدیل ``"5.0.0"`` به تاپل؛ ورودی نامعتبر ← None."""
    match = _SEMVER.match((raw or "").strip())
    if not match:
        return None
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def is_valid_version(raw: str) -> bool:
    return parse_version(raw) is not None


def version_tuple() -> tuple[int, int, int]:
    parsed = parse_version(__version__)
    return parsed or (0, 0, 0)


def version_line() -> str:
    """متن کوتاه برای لاگ و پیام‌ها."""
    return f"v{__version__} “{CODENAME}” ({RELEASE_DATE})"


def version_badge() -> str:
    """نسخهٔ قابل‌نمایش در پیام‌های تلگرام."""
    return f"🤖 <b>LeechX v{__version__}</b> · {CODENAME}"


def bump(kind: str = "patch") -> str:
    """نسخهٔ بعدی را برمی‌گرداند (بدون نوشتن فایل).

    برای استفادهٔ ابزارهای توسعه/هوش مصنوعی: ``python -m app.version minor``
    """
    major, minor, patch = version_tuple()
    if kind == "major":
        major, minor, patch = major + 1, 0, 0
    elif kind == "minor":
        minor, patch = minor + 1, 0
    elif kind == "patch":
        patch += 1
    else:
        raise ValueError("kind must be major, minor or patch")
    return f"{major}.{minor}.{patch}"


if __name__ == "__main__":  # pragma: no cover - ابزار خط فرمان
    import sys

    arg = sys.argv[1] if len(sys.argv) > 1 else "show"
    if arg in ("major", "minor", "patch"):
        print(bump(arg))
    else:
        print(version_line())

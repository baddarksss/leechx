"""نسخهٔ دقیق: ``app/version.py`` باید با ``pyproject.toml`` و ``CHANGELOG.md`` یکی باشد."""
from __future__ import annotations

import re
from pathlib import Path

from app import version

ROOT = Path(__file__).resolve().parents[1]


def _pyproject_version() -> str:
    raw = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', raw, re.MULTILINE)
    assert match, "version not found in pyproject.toml"
    return match.group(1)


def _changelog_version() -> str:
    raw = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(r"^##\s*\[([0-9]+\.[0-9]+\.[0-9]+)\]", raw, re.MULTILINE)
    assert match, "no versioned entry found in CHANGELOG.md"
    return match.group(1)


def test_version_is_semver():
    assert version.is_valid_version(version.__version__)
    assert version.parse_version(version.__version__) == version.version_tuple()


def test_version_matches_pyproject_and_changelog():
    assert _pyproject_version() == version.__version__
    assert _changelog_version() == version.__version__


def test_version_helpers_render_current_version():
    assert version.__version__ in version.version_line()
    assert version.__version__ in version.version_badge()
    assert version.CODENAME in version.version_line()


def test_bump_produces_next_semver():
    major, minor, patch = version.version_tuple()
    assert version.bump("major") == f"{major + 1}.0.0"
    assert version.bump("minor") == f"{major}.{minor + 1}.0"
    assert version.bump("patch") == f"{major}.{minor}.{patch + 1}"

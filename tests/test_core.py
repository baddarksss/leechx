from app.core.human import human_bytes, human_duration, progress_bar, safe_filename
from app.core.urlcheck import (
    extract_urls,
    filename_from_url,
    host_of,
    is_valid_url,
    looks_archive,
    looks_direct,
    path_extension,
)


def test_extract_urls_basic():
    text = "ببین https://youtu.be/abc123 و http://x.com/a?b=1."
    assert extract_urls(text) == ["https://youtu.be/abc123", "http://x.com/a?b=1"]


def test_extract_urls_dedup_and_limit():
    text = " ".join(f"https://a.com/{i}" for i in range(10))
    urls = extract_urls(text)
    assert len(urls) == 5
    assert urls[0] == "https://a.com/0"


def test_extract_urls_ignores_bad():
    assert extract_urls("ftp://x.com/a file:///c:/x") == []
    assert extract_urls(None) == []
    assert extract_urls("") == []


def test_is_valid_url():
    assert is_valid_url("https://ok.com")
    assert not is_valid_url("not a url")
    assert not is_valid_url("javascript:alert(1)")


def test_host_and_ext():
    assert host_of("https://www.YouTube.com/watch?v=1") == "youtube.com"
    assert path_extension("https://x.com/a/B.MP4?sig=1") == ".mp4"
    assert filename_from_url("https://x.com/a/My%20Film.mp4") == "My Film.mp4"


def test_looks_direct():
    assert looks_direct("https://x.com/a.mp4")
    assert looks_direct("https://x.com/a.MP3")
    assert not looks_direct("https://youtube.com/watch?v=abc")
    assert looks_archive("https://x.com/a.zip")
    assert not looks_archive("https://x.com/a.mp4")


def test_human_helpers():
    assert human_bytes(0) == "0 B"
    assert human_bytes(999) == "999 B"
    assert human_bytes(1024) == "1 KB"
    assert human_bytes(1536) == "1.5 KB"
    assert human_duration(0) == "—"
    assert human_duration(65) == "1:05"
    assert human_duration(3661) == "1:01:01"
    assert progress_bar(0).split() == ["⬜"] * 10
    assert progress_bar(50).split() == ["🟩"] * 5 + ["⬜"] * 5
    assert progress_bar(100).split() == ["🟩"] * 10
    bar = progress_bar(50, show_pct=True).split("\n")
    assert bar[0].split() == ["🟩"] * 5 + ["⬜"] * 5
    assert bar[1] == "50%"
    assert progress_bar(99.9, show_pct=True).endswith("\n99%")


def test_safe_filename():
    assert safe_filename('a/b\\c:d*e?f"g<h>i|j') == "a_b_c_d_e_f_g_h_i_j"
    assert safe_filename("") == "file"
    assert len(safe_filename("x" * 500)) <= 120
    assert safe_filename("  spaced  name  ") == "spaced name"

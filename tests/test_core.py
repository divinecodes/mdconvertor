from pathlib import Path

import pytest

from mdconvertor import core


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path: Path, monkeypatch):
    monkeypatch.setenv(core.CACHE_ENV, str(tmp_path / "cache"))
    monkeypatch.delenv(core.ROOTS_ENV, raising=False)


def test_outline_records_levels_and_line_numbers():
    md = "# One\n\ntext\n\n## Two\n\n### Three\n"
    outline = core.parse_outline(md)
    assert [(h.level, h.line, h.text) for h in outline.headings] == [
        (1, 1, "One"),
        (2, 5, "Two"),
        (3, 7, "Three"),
    ]
    assert outline.truncated is False


def test_outline_ignores_headings_inside_code_fences():
    md = "# Real\n\n```python\n# not a heading\n## also not\n```\n\n## Also real\n"
    assert [h.text for h in core.parse_outline(md).headings] == ["Real", "Also real"]


def test_outline_ignores_closing_hashes_and_empty_headings():
    md = "# Title #\n\n#\n\n#nospace\n"
    assert [h.text for h in core.parse_outline(md).headings] == ["Title"]


def test_outline_drops_deep_headings_before_truncating():
    md = "".join(f"### Deep {i}\n" for i in range(50)) + "# Top\n"
    outline = core.parse_outline(md, max_entries=10)
    assert outline.truncated is True
    assert [h.text for h in outline.headings] == ["Top"]


def test_outline_truncates_when_even_shallow_is_too_many():
    md = "".join(f"# Head {i}\n" for i in range(40))
    outline = core.parse_outline(md, max_entries=10)
    assert outline.truncated is True
    assert len(outline.headings) == 10


def test_numbered_fallback_when_there_are_no_markdown_headings():
    md = "Preamble\n\n1. Introduction\n\ntext\n\n2.3. The Magic Files\n\nmore\n"
    outline = core.parse_outline(md)
    assert [(h.level, h.line, h.text) for h in outline.headings] == [
        (1, 3, "1. Introduction"),
        (2, 7, "2.3. The Magic Files"),
    ]


def test_numbered_fallback_is_not_used_when_real_headings_exist():
    md = "# Real\n\n1. an ordinary numbered list item\n"
    assert [h.text for h in core.parse_outline(md).headings] == ["Real"]


def test_numbered_fallback_rejects_prose_years_and_long_lines():
    md = (
        "1. lowercase start is probably a list item\n"
        "2. " + "Long " * 40 + "\n"
        "1999. Probably A Bibliography Year\n"
        "3. A Real Section\n"
    )
    assert [h.text for h in core.parse_outline(md).headings] == ["3. A Real Section"]


def test_estimate_tokens():
    assert core.estimate_tokens("a" * 400) == 100


def test_scanned_warning_only_for_big_source_with_no_text():
    assert core.scanned_warning("", 500_000) is not None
    assert core.scanned_warning("", 10) is None
    assert core.scanned_warning("x" * 1000, 500_000) is None


def test_cache_key_follows_content_not_name(tmp_path: Path):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("same", encoding="utf-8")
    b.write_text("same", encoding="utf-8")
    c = tmp_path / "c.txt"
    c.write_text("different", encoding="utf-8")

    assert core.cache_key(a) == core.cache_key(b)
    assert core.cache_key(a) != core.cache_key(c)
    assert core.cache_key(a) != core.cache_key(a, plugins=True)


def test_cache_key_for_urls_uses_the_url():
    assert core.cache_key("https://example.com/a.pdf") == core.cache_key(
        "https://example.com/a.pdf"
    )
    assert core.cache_key("https://example.com/a.pdf") != core.cache_key(
        "https://example.com/b.pdf"
    )


def test_store_and_load_cached():
    assert core.load_cached("deadbeef") is None
    path = core.store_cached("deadbeef", "# Hi", {"title": "Hi"})
    assert path.read_text(encoding="utf-8") == "# Hi"

    loaded = core.load_cached("deadbeef")
    assert loaded is not None
    loaded_path, meta = loaded
    assert loaded_path == path
    assert meta["title"] == "Hi"


def test_load_cached_survives_corrupt_metadata():
    core.store_cached("beef", "# Hi", {"title": "Hi"})
    _, meta_path = core.cache_paths("beef")
    meta_path.write_text("{not json", encoding="utf-8")

    loaded = core.load_cached("beef")
    assert loaded is not None
    assert loaded[1] == {}


def test_clear_cache_counts_documents():
    core.store_cached("aaaa", "# A", {})
    core.store_cached("bbbb", "# B", {})
    assert core.clear_cache() == 2
    assert core.clear_cache() == 0


def test_allowed_roots_guard(tmp_path: Path, monkeypatch):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    inside = allowed / "ok.txt"
    inside.write_text("hi", encoding="utf-8")
    outside = tmp_path / "nope.txt"
    outside.write_text("hi", encoding="utf-8")

    core.check_allowed(outside)  # unset: anything goes

    monkeypatch.setenv(core.ROOTS_ENV, str(allowed))
    core.check_allowed(inside)
    with pytest.raises(core.ConversionError):
        core.check_allowed(outside)


def test_convert_markdown_wraps_failures(tmp_path: Path):
    with pytest.raises(core.ConversionError):
        core.convert_markdown(tmp_path / "missing.pdf")


def test_is_url():
    assert core.is_url("https://example.com")
    assert core.is_url("http://example.com")
    assert not core.is_url("/tmp/file.pdf")

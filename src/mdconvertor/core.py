"""Conversion, outline parsing and caching shared by the CLI and the MCP server."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import time
import warnings
from dataclasses import dataclass
from pathlib import Path

CACHE_ENV = "MDCONVERTOR_CACHE_DIR"
ROOTS_ENV = "MDCONVERTOR_ALLOWED_ROOTS"
HASH_CHUNK = 1024 * 1024
KEY_LENGTH = 16

# A conversion this short from a source this large almost always means the
# document is scanned images that markitdown cannot read as text.
EMPTY_OUTPUT_CHARS = 200
LARGE_SOURCE_BYTES = 100_000

ATX_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
CODE_FENCE = re.compile(r"^\s*(```|~~~)")

# markitdown's PDF converter emits plain text with no '#' headings at all, so
# PDFs -- the main thing this tool is pointed at -- would otherwise get an empty
# outline and no way for an agent to read selectively. Most real documents
# number their sections, so fall back to detecting "2.3. Some Title" lines.
NUMBERED_HEADING = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+([A-Z].*\S)$")
NUMBERED_MAX_CHARS = 100
# Keeps years out: "1999. Some Capitalised Line" in a bibliography is not a section.
NUMBERED_MAX_SECTION = 99


class ConversionError(RuntimeError):
    """Raised when a source cannot be converted or is not permitted."""


@dataclass
class Heading:
    level: int
    line: int
    text: str


@dataclass
class Outline:
    headings: list[Heading]
    truncated: bool


def is_url(source: str) -> bool:
    return source.startswith(("http://", "https://"))


def allowed_roots() -> list[Path]:
    raw = os.environ.get(ROOTS_ENV, "").strip()
    if not raw:
        return []
    return [Path(p).expanduser().resolve() for p in raw.split(os.pathsep) if p]


def check_allowed(source: Path) -> None:
    """Reject sources outside MDCONVERTOR_ALLOWED_ROOTS when that is configured."""
    roots = allowed_roots()
    if not roots:
        return
    resolved = source.resolve()
    if not any(resolved == root or root in resolved.parents for root in roots):
        raise ConversionError(f"{source} is outside the allowed roots")


def convert_markdown(source: str | Path, *, plugins: bool = False) -> tuple[str, str | None]:
    """Convert a file path or URL, returning (markdown, title)."""
    # Imported lazily: markitdown[all] pulls in pandas and friends, which makes
    # --help and --version noticeably slow if imported at module level. The
    # warning filter hides pydub's "couldn't find ffmpeg" notice, which is
    # irrelevant unless you are converting audio.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        from markitdown import MarkItDown

    md = MarkItDown(enable_plugins=plugins)
    try:
        if isinstance(source, str) and is_url(source):
            result = md.convert_uri(source)
        else:
            result = md.convert(str(source))
    except Exception as exc:  # markitdown raises several conversion error types
        raise ConversionError(f"failed to convert {source}: {exc}") from exc
    return result.markdown, result.title


def estimate_tokens(text: str) -> int:
    """Rough token count. Deliberately a heuristic to avoid a tokenizer dependency."""
    return len(text) // 4


def parse_outline(markdown: str, *, max_entries: int = 40) -> Outline:
    """Collect ATX headings with their 1-indexed line numbers.

    Headings inside fenced code blocks are skipped -- a Python comment such as
    `# TODO` would otherwise show up as a top level heading. When there are more
    headings than `max_entries`, drop to h1/h2 only before truncating, so the
    outline stays a useful index instead of a wall of subsections.

    The cap is what bounds the size of an MCP tool result: without it the
    outline would grow with the document, and a receipt that scales with the
    document defeats the point of not returning the document.
    """
    headings = _atx_headings(markdown) or _numbered_headings(markdown)

    if len(headings) <= max_entries:
        return Outline(headings=headings, truncated=False)

    shallow = [h for h in headings if h.level <= 2]
    if len(shallow) <= max_entries:
        return Outline(headings=shallow, truncated=True)
    return Outline(headings=shallow[:max_entries], truncated=True)


def _atx_headings(markdown: str) -> list[Heading]:
    headings: list[Heading] = []
    fence: str | None = None

    for number, line in enumerate(markdown.splitlines(), start=1):
        fence_match = CODE_FENCE.match(line)
        if fence_match:
            marker = fence_match.group(1)
            if fence is None:
                fence = marker
            elif line.strip().startswith(fence):
                fence = None
            continue
        if fence is not None:
            continue
        match = ATX_HEADING.match(line)
        if match and match.group(2):
            headings.append(
                Heading(level=len(match.group(1)), line=number, text=match.group(2))
            )
    return headings


def _numbered_headings(markdown: str) -> list[Heading]:
    """Detect "1.", "2.3." style section headings in documents with no markup.

    Deliberately strict -- a capitalised start and a short line -- because the
    alternative to a missed heading is a false one, and a false heading sends an
    agent to read the wrong lines.
    """
    headings: list[Heading] = []
    for number, line in enumerate(markdown.splitlines(), start=1):
        stripped = line.strip()
        if len(stripped) > NUMBERED_MAX_CHARS:
            continue
        match = NUMBERED_HEADING.match(stripped)
        if match:
            parts = match.group(1).split(".")
            if int(parts[0]) > NUMBERED_MAX_SECTION:
                continue
            headings.append(Heading(level=len(parts), line=number, text=stripped))
    return headings


def scanned_warning(markdown: str, source_bytes: int) -> str | None:
    """Flag the silent failure mode: a big source that yields almost no text."""
    if len(markdown.strip()) < EMPTY_OUTPUT_CHARS and source_bytes > LARGE_SOURCE_BYTES:
        return (
            "conversion produced almost no text; the source is probably scanned "
            "images and needs OCR"
        )
    return None


def cache_dir() -> Path:
    override = os.environ.get(CACHE_ENV)
    if override:
        return Path(override).expanduser()
    base = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(base).expanduser() / "mdconvertor"


def cache_key(source: str | Path, *, plugins: bool = False) -> str:
    """Content hash for files, URL hash for URLs.

    Hashing content rather than the path means a renamed or moved file still
    hits the cache. URLs can only be keyed on the URL itself, so their entries
    do not notice upstream changes -- callers pass force=True to re-fetch.
    """
    digest = hashlib.sha256()
    digest.update(b"plugins=1" if plugins else b"plugins=0")
    if isinstance(source, str) and is_url(source):
        digest.update(source.encode("utf-8"))
    else:
        with open(source, "rb") as handle:
            while chunk := handle.read(HASH_CHUNK):
                digest.update(chunk)
    return digest.hexdigest()[:KEY_LENGTH]


def cache_paths(key: str) -> tuple[Path, Path]:
    directory = cache_dir()
    return directory / f"{key}.md", directory / f"{key}.json"


def load_cached(key: str) -> tuple[Path, dict] | None:
    markdown_path, meta_path = cache_paths(key)
    if not markdown_path.exists():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        meta = {}
    return markdown_path, meta


def store_cached(key: str, markdown: str, meta: dict) -> Path:
    markdown_path, meta_path = cache_paths(key)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(markdown, encoding="utf-8")
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return markdown_path


def source_metadata(source: str | Path) -> dict:
    meta = {"source": str(source), "converted_at": time.time()}
    if not (isinstance(source, str) and is_url(source)):
        stat = Path(source).stat()
        meta["source_bytes"] = stat.st_size
        meta["source_mtime"] = stat.st_mtime
    return meta


def clear_cache() -> int:
    """Delete the cache directory. Returns the number of converted documents removed."""
    directory = cache_dir()
    if not directory.exists():
        return 0
    count = len(list(directory.glob("*.md")))
    shutil.rmtree(directory)
    return count

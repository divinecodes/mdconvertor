"""MCP server exposing document-to-Markdown conversion to an LLM agent.

The design goal is token thrift. Returning the converted document from the tool
would put the entire text into the model's context on every call, which is the
cost this server exists to avoid. So conversion is treated as a side effect: the
Markdown goes to a cache file and the tool returns only a receipt describing it.
"""

from __future__ import annotations

from pathlib import Path

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from . import __version__
from .core import (
    ConversionError,
    cache_key,
    check_allowed,
    convert_markdown,
    count_lines,
    estimate_tokens,
    is_url,
    load_cached,
    parse_outline,
    scanned_warning,
    source_metadata,
    store_cached,
)

PREVIEW_CHARS = 200

mcp = MCPServer("mdconvertor")


class HeadingEntry(BaseModel):
    level: int = Field(description="Heading depth, 1 for '#' through 6 for '######'.")
    line: int = Field(description="1-indexed line number of the heading in the file.")
    text: str = Field(description="Heading text.")


class ConvertResult(BaseModel):
    path: str = Field(description="Absolute path to the converted Markdown file.")
    bytes: int = Field(description="Size of the Markdown file.")
    lines: int = Field(description="Total lines, the upper bound for a read offset.")
    est_tokens: int = Field(
        description="Approximate tokens if the whole file were read (chars/4)."
    )
    title: str | None = Field(default=None, description="Document title, when detected.")
    outline: list[HeadingEntry] = Field(
        default_factory=list,
        description="Headings with line numbers. Use these to read only what you need.",
    )
    outline_truncated: bool = Field(
        default=False, description="True when the outline was capped for size."
    )
    preview: str = Field(default="", description="First 200 characters, to sanity check.")
    cached: bool = Field(
        default=False, description="True when served from cache without reconverting."
    )
    warning: str | None = Field(
        default=None, description="Set when the conversion looks unusable."
    )


@mcp.tool(
    title="Convert document to Markdown",
    description=(
        "Convert a document (PDF, Word, PowerPoint, Excel, HTML, EPUB, images, "
        "audio, and more) to Markdown. Accepts a local file path or an http(s) URL.\n"
        "\n"
        "IMPORTANT: this returns a FILE PATH, not the document text. The converted "
        "Markdown is written to disk and this tool reports where it is, how big it "
        "is, and its heading outline with line numbers. Read the file yourself with "
        "your own file-reading tool.\n"
        "\n"
        "To stay cheap, do not read the whole file unless est_tokens is small. Use "
        "the outline's line numbers to read only the sections relevant to the task "
        "(e.g. read from the line of the heading you want up to the line of the next "
        "one), or grep the file for a term. Repeat calls on the same document are "
        "served from cache for free; pass force=true to reconvert."
    ),
    annotations=ToolAnnotations(
        read_only_hint=False,  # writes into the conversion cache
        idempotent_hint=True,
        open_world_hint=True,  # can fetch URLs
    ),
)
def convert_to_markdown(source: str, force: bool = False) -> ConvertResult:
    """Convert a document and return where the Markdown landed."""
    source_is_url = is_url(source)

    if not source_is_url:
        path = Path(source).expanduser()
        if not path.exists():
            raise ConversionError(f"no such file: {source}")
        if not path.is_file():
            raise ConversionError(f"not a file: {source}")
        check_allowed(path)
        source = str(path)

    key = cache_key(source)
    cached = None if force else load_cached(key)

    if cached is not None:
        out_path, meta = cached
        markdown = out_path.read_text(encoding="utf-8")
        title = meta.get("title")
        was_cached = True
    else:
        markdown, title = convert_markdown(source)
        meta = source_metadata(source)
        meta["title"] = title
        meta["mdconvertor_version"] = __version__
        out_path = store_cached(key, markdown, meta)
        was_cached = False

    outline = parse_outline(markdown)
    source_bytes = meta.get("source_bytes", 0) if isinstance(meta, dict) else 0

    return ConvertResult(
        path=str(out_path.resolve()),
        bytes=len(markdown.encode("utf-8")),
        lines=count_lines(markdown),
        est_tokens=estimate_tokens(markdown),
        title=title,
        outline=[
            HeadingEntry(level=h.level, line=h.line, text=h.text) for h in outline.headings
        ],
        outline_truncated=outline.truncated,
        preview=markdown.strip()[:PREVIEW_CHARS],
        cached=was_cached,
        warning=scanned_warning(markdown, source_bytes),
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()

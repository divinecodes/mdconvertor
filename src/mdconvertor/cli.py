"""Command line entry point for mdconv."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import __version__
from .core import ConversionError, clear_cache, convert_markdown

STDOUT = "-"


def resolve_output(source: Path, dest: str) -> Path | None:
    """Work out where the Markdown should go.

    Returns None when the destination is stdout. A destination is treated as a
    directory when it already is one, when it ends with a separator, or when it
    has no suffix; otherwise it is used verbatim as the output file.
    """
    if dest == STDOUT:
        return None

    dest_path = Path(dest)
    looks_like_dir = (
        dest_path.is_dir()
        or dest.endswith((os.sep, "/"))
        or not dest_path.suffix
    )
    if looks_like_dir:
        return dest_path / (source.stem + ".md")
    return dest_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mdconv",
        description="Convert a file to Markdown using markitdown.",
    )
    parser.add_argument("source", nargs="?", help="file to convert")
    parser.add_argument(
        "dest",
        nargs="?",
        default=".",
        help="output directory, output .md path, or - for stdout (default: .)",
    )
    parser.add_argument(
        "-f", "--force", action="store_true", help="overwrite an existing output file"
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="do not print the output path"
    )
    parser.add_argument(
        "--plugins", action="store_true", help="enable markitdown plugins"
    )
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="delete the conversion cache used by the MCP server and exit",
    )
    parser.add_argument("--version", action="version", version=f"mdconv {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.clear_cache:
        removed = clear_cache()
        print(f"cleared {removed} cached conversion(s)", file=sys.stderr)
        return 0

    if args.source is None:
        parser.error("the following arguments are required: source")

    source = Path(args.source)
    if not source.is_file():
        print(f"error: no such file: {source}", file=sys.stderr)
        return 2

    out = resolve_output(source, args.dest)
    if out is not None:
        if out.resolve() == source.resolve():
            print(f"error: refusing to overwrite the source file: {source}", file=sys.stderr)
            return 1
        if out.exists() and not args.force:
            print(
                f"error: {out} already exists (use --force to overwrite)",
                file=sys.stderr,
            )
            return 1

    try:
        markdown, _title = convert_markdown(source, plugins=args.plugins)
    except ConversionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if out is None:
        sys.stdout.write(markdown)
        return 0

    if out.parent != Path(""):
        out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(markdown, encoding="utf-8")
    if not args.quiet:
        print(f"wrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Command line entry point for mdconv."""

from __future__ import annotations

import argparse
import os
import sys
import warnings
from pathlib import Path

from . import __version__

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
    parser.add_argument("source", help="file to convert")
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
    parser.add_argument("--version", action="version", version=f"mdconv {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

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

    # Imported lazily: markitdown[all] pulls in pandas and friends, which makes
    # --help and --version noticeably slow if imported at module level. The
    # warning filter hides pydub's "couldn't find ffmpeg" notice, which is
    # irrelevant unless you are converting audio.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        from markitdown import MarkItDown

    try:
        result = MarkItDown(enable_plugins=args.plugins).convert(str(source))
    except Exception as exc:  # markitdown raises several conversion error types
        print(f"error: failed to convert {source}: {exc}", file=sys.stderr)
        return 1

    if out is None:
        sys.stdout.write(result.markdown)
        return 0

    if out.parent != Path(""):
        out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(result.markdown, encoding="utf-8")
    if not args.quiet:
        print(f"wrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

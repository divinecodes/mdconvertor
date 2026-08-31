# Contributing

Thanks for taking a look. Issues and pull requests are both welcome.

## Getting set up

The project uses [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/divinecodes/mdconvertor
cd mdconvertor
uv sync --extra mcp
uv run pytest -q
```

That is the whole setup. `uv sync` reads `uv.lock`, so you get the same
dependency versions CI does.

Two quirks worth knowing before they surprise you:

- **Pre-releases are enabled** (`[tool.uv] prerelease = "allow"`). `markitdown[all]`
  depends on a beta Azure SDK, so resolution fails without it. That setting covers
  `uv sync` but *not* `uv tool install`, which needs `--prerelease=allow` passed
  explicitly.
- **Python 3.14 does not work here.** `markitdown` pins `magika~=0.6.1`, which caps
  `onnxruntime` at 1.20.1 on Windows; that release has no 3.14 wheels, and the
  lockfile is universal, so it has to satisfy Windows too. Supported range is
  3.10–3.13, and `.python-version` pins 3.12 for local work.

## Running the pieces

```bash
uv run mdconv report.pdf .          # the CLI
uv run mdconv-mcp                   # the MCP server, on stdio
uv run pytest -q tests/test_mcp.py  # the server, in process, over the real protocol
```

`tests/test_mcp.py` drives the server through `mcp.Client` with an in-memory
transport, so there is no subprocess to manage and no config file to point at a
checkout.

## Tests

CI runs `uv run pytest` on 3.10–3.13 (Linux) plus 3.12 on macOS and Windows.
Please add a test with a behaviour change.

One piece of hard-won context on fixtures: **HTML fixtures do not exercise the
PDF path.** markitdown's PDF converter takes one of two branches — pdfplumber
when a page has form or table content, pdfminer otherwise — and only the
pdfminer branch emits the form feeds that page boundaries produce. An outline
line-numbering bug survived a full green suite because every fixture was HTML.
If you touch outline parsing or line counting, use text containing `\f`; see
`PAGED_PDF_TEXT` in `tests/test_core.py`.

## Things to keep in mind

- **The MCP tool must never return document text.** The whole point of the
  server is that the body stays on disk and out of the model's context. Two
  tests guard this (`test_document_body_never_enters_the_result` and
  `test_receipt_size_does_not_grow_with_the_document`); if a change makes them
  fail, the change is wrong, not the tests.
- **Keep it to one tool.** Tool definitions are re-sent on every request, so the
  tool surface is a running token cost. Cache maintenance is a human action and
  lives on the CLI.
- **Anticipated failures raise `ToolError`.** Any other exception is masked by
  the SDK to `Error executing tool convert_to_markdown`, which tells an agent
  nothing it can act on.
- Line numbers in an outline must match what a plain file reader sees. Split on
  `\n`, never `str.splitlines()`.

## Commit messages

Say what changed and why the change was needed. If you fixed a bug, the message
should make clear what was broken and how it showed up.

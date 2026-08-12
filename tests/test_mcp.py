from pathlib import Path

import pytest
from mcp import Client

from mdconvertor import core
from mdconvertor.mcp_server import mcp

# Placed deep in the document, well past the 200-char preview window, so that
# finding it in a tool result means the body genuinely leaked.
BODY_MARKER = "supercalifragilistic"
HTML = (
    "<h1>Report</h1>"
    + "<p>filler paragraph for padding</p>" * 40
    + f"<h2>Details</h2><p>{BODY_MARKER}</p>"
)


def tool_error_text(result) -> str:
    return " ".join(block.text for block in result.content)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path: Path, monkeypatch):
    monkeypatch.setenv(core.CACHE_ENV, str(tmp_path / "cache"))
    monkeypatch.delenv(core.ROOTS_ENV, raising=False)


@pytest.fixture
def sample(tmp_path: Path) -> Path:
    src = tmp_path / "report.html"
    src.write_text(HTML, encoding="utf-8")
    return src


@pytest.fixture
def big_sample(tmp_path: Path) -> Path:
    """A document large enough that dumping it into context would actually hurt."""
    src = tmp_path / "big.html"
    body = "".join(
        f"<h2>Section {i}</h2><p>{'lorem ipsum dolor sit amet ' * 20}</p>"
        for i in range(80)
    )
    src.write_text(f"<h1>Big Report</h1>{body}<p>{BODY_MARKER}</p>", encoding="utf-8")
    return src


@pytest.fixture
async def client():
    async with Client(mcp, raise_exceptions=True) as c:
        yield c


@pytest.mark.anyio
async def test_exposes_a_single_tool(client: Client):
    tools = await client.list_tools()
    assert [t.name for t in tools.tools] == ["convert_to_markdown"]


@pytest.mark.anyio
async def test_returns_a_path_and_outline(client: Client, sample: Path):
    result = await client.call_tool("convert_to_markdown", {"source": str(sample)})
    data = result.structured_content

    assert Path(data["path"]).is_file()
    assert data["lines"] > 0
    assert data["est_tokens"] > 0
    assert data["cached"] is False
    assert [(h["level"], h["text"]) for h in data["outline"]] == [
        (1, "Report"),
        (2, "Details"),
    ]
    assert "# Report" in Path(data["path"]).read_text(encoding="utf-8")


@pytest.mark.anyio
async def test_document_body_never_enters_the_result(client: Client, big_sample: Path):
    """The entire point of the server: the text stays on disk, out of context."""
    result = await client.call_tool("convert_to_markdown", {"source": str(big_sample)})
    data = result.structured_content
    serialized = result.model_dump_json()

    # The marker sits at the end of the document, far past the preview window;
    # it must reach the agent only via the file on disk.
    assert BODY_MARKER in Path(data["path"]).read_text(encoding="utf-8")
    assert BODY_MARKER not in serialized

    assert data["bytes"] > 30_000
    assert len(serialized) < data["bytes"] // 4


@pytest.mark.anyio
async def test_receipt_size_does_not_grow_with_the_document(
    client: Client, tmp_path: Path
):
    """The invariant that makes this worth doing: cost is flat in document size.

    A receipt that scaled with the document would be no better than returning
    the text. The outline cap and fixed-length preview are what bound it.
    """

    async def receipt_size(sections: int) -> tuple[int, int]:
        src = tmp_path / f"doc{sections}.html"
        body = "".join(
            f"<h2>Section {i}</h2><p>{'lorem ipsum dolor sit amet ' * 20}</p>"
            for i in range(sections)
        )
        src.write_text(f"<h1>Doc</h1>{body}", encoding="utf-8")
        result = await client.call_tool("convert_to_markdown", {"source": str(src)})
        return len(result.model_dump_json()), result.structured_content["bytes"]

    small_receipt, small_doc = await receipt_size(40)
    large_receipt, large_doc = await receipt_size(400)

    assert large_doc > small_doc * 5
    assert large_receipt < small_receipt * 1.5


@pytest.mark.anyio
async def test_second_call_is_served_from_cache(client: Client, sample: Path):
    first = await client.call_tool("convert_to_markdown", {"source": str(sample)})
    second = await client.call_tool("convert_to_markdown", {"source": str(sample)})
    assert first.structured_content["cached"] is False
    assert second.structured_content["cached"] is True
    assert first.structured_content["path"] == second.structured_content["path"]

    forced = await client.call_tool(
        "convert_to_markdown", {"source": str(sample), "force": True}
    )
    assert forced.structured_content["cached"] is False


@pytest.mark.anyio
async def test_missing_source_is_an_error(client: Client, tmp_path: Path):
    result = await client.call_tool(
        "convert_to_markdown", {"source": str(tmp_path / "nope.pdf")}
    )
    assert result.is_error is True
    assert "no such file" in tool_error_text(result)


@pytest.mark.anyio
async def test_respects_allowed_roots(client: Client, sample: Path, monkeypatch, tmp_path):
    monkeypatch.setenv(core.ROOTS_ENV, str(tmp_path / "elsewhere"))
    result = await client.call_tool("convert_to_markdown", {"source": str(sample)})
    assert result.is_error is True
    assert "outside the allowed roots" in tool_error_text(result)

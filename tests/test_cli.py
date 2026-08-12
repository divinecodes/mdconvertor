from pathlib import Path

import pytest

from mdconvertor.cli import main, resolve_output

HTML = "<h1>Hi</h1><p>Body</p>"


@pytest.fixture
def sample(tmp_path: Path) -> Path:
    src = tmp_path / "report.html"
    src.write_text(HTML, encoding="utf-8")
    return src


def test_resolve_output_dot(tmp_path: Path):
    src = tmp_path / "report.pdf"
    assert resolve_output(src, ".") == Path("report.md")


def test_resolve_output_missing_directory():
    assert resolve_output(Path("report.pdf"), "out/") == Path("out/report.md")
    assert resolve_output(Path("report.pdf"), "out") == Path("out/report.md")


def test_resolve_output_explicit_file():
    assert resolve_output(Path("report.pdf"), "out/notes.md") == Path("out/notes.md")


def test_resolve_output_stdout():
    assert resolve_output(Path("report.pdf"), "-") is None


def test_converts_into_directory(sample: Path, tmp_path: Path):
    assert main([str(sample), str(tmp_path)]) == 0
    out = tmp_path / "report.md"
    assert "# Hi" in out.read_text(encoding="utf-8")


def test_converts_to_explicit_path(sample: Path, tmp_path: Path):
    out = tmp_path / "nested" / "notes.md"
    assert main([str(sample), str(out)]) == 0
    assert "# Hi" in out.read_text(encoding="utf-8")


def test_converts_to_stdout(sample: Path, capsys):
    assert main([str(sample), "-"]) == 0
    assert "# Hi" in capsys.readouterr().out


def test_stdout_survives_a_closed_pipe(sample: Path, monkeypatch, capsys):
    """`mdconv file.pdf - | head` must not end in a BrokenPipeError traceback."""

    class ClosedPipe:
        def write(self, _text):
            raise BrokenPipeError

        def flush(self):
            raise BrokenPipeError

        def fileno(self):
            return 1

    monkeypatch.setattr("sys.stdout", ClosedPipe())
    monkeypatch.setattr("os.dup2", lambda *_: None)
    assert main([str(sample), "-"]) == 141


def test_refuses_to_overwrite(sample: Path, tmp_path: Path):
    out = tmp_path / "report.md"
    out.write_text("keep me", encoding="utf-8")

    assert main([str(sample), str(tmp_path)]) == 1
    assert out.read_text(encoding="utf-8") == "keep me"

    assert main([str(sample), str(tmp_path), "--force"]) == 0
    assert "# Hi" in out.read_text(encoding="utf-8")


def test_refuses_to_overwrite_source(tmp_path: Path):
    src = tmp_path / "notes.md"
    src.write_text("# original", encoding="utf-8")
    assert main([str(src), str(tmp_path)]) == 1
    assert src.read_text(encoding="utf-8") == "# original"


def test_missing_source(tmp_path: Path):
    assert main([str(tmp_path / "nope.pdf"), str(tmp_path)]) == 2

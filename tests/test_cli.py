"""CLI tests for behavior that does not require parser-context fixtures."""

from __future__ import annotations

from table1_parser import cli


def test_cli_extract_missing_pdf_fails_gracefully(capsys) -> None:
    """The extract command should fail gracefully on a missing PDF."""
    exit_code = cli.main(["extract", "paper.pdf"])

    captured = capsys.readouterr()

    assert exit_code == 1
    assert "error" in captured.err

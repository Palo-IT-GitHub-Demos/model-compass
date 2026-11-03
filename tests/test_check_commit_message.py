"""Tests for the local commit-message validator."""

from __future__ import annotations

from scripts.check_commit_message import validate_commit_message


def test_accepts_a_conventional_commit_header() -> None:
    assert validate_commit_message("feat(compass): use fixed score scales\n\nDetails.\n") == []


def test_ignores_git_comment_lines_before_the_header() -> None:
    assert validate_commit_message("# Please enter the commit message\n\nfix: retry timeouts\n") == []


def test_rejects_unknown_types_and_uppercase_subjects() -> None:
    errors = validate_commit_message("Feature(compass): Add score scales")

    assert "use <allowed-type>(optional-scope): <lower-case subject>" in errors


def test_rejects_subject_period() -> None:
    assert "subject must not end with a period" in validate_commit_message("fix: correct a score.")


def test_rejects_headers_over_72_characters() -> None:
    message = "docs: " + "a" * 67

    assert any("maximum is 72" in error for error in validate_commit_message(message))


def test_rejects_an_empty_message() -> None:
    assert validate_commit_message("# comment\n\n") == ["commit message header is empty"]

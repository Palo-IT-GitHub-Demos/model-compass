"""Tests for splitting blind judging batches into forwardable parts."""

from __future__ import annotations

import json
from pathlib import Path

from src.pipeline_artifacts import write_judging_parts


def _batch(item_count: int, response_chars: int) -> dict[str, object]:
    return {
        "timestamp": "20260101_000000",
        "pending_judgments": [
            {"prompt_id": index, "attempt": 0, "responses": {"A": "x" * response_chars}} for index in range(item_count)
        ],
    }


def test_small_batch_is_not_split(tmp_path: Path) -> None:
    assert write_judging_parts(_batch(2, 100), tmp_path, max_chars=10_000) == []
    assert list(tmp_path.iterdir()) == []


def test_large_batch_is_split_in_order_without_cutting_an_item(tmp_path: Path) -> None:
    parts = write_judging_parts(_batch(5, 1_000), tmp_path, max_chars=2_500)

    assert [part.name for part in parts] == [
        "judging_20260101_000000_part01of03.json",
        "judging_20260101_000000_part02of03.json",
        "judging_20260101_000000_part03of03.json",
    ]
    payloads = [json.loads(part.read_text()) for part in parts]
    assert [item["prompt_id"] for payload in payloads for item in payload["pending_judgments"]] == [0, 1, 2, 3, 4]
    assert {payload["timestamp"] for payload in payloads} == {"20260101_000000"}
    assert [payload["part"] for payload in payloads] == [1, 2, 3]
    assert all(len(part.read_text()) <= 2_500 + 200 for part in parts)


def test_an_oversized_item_gets_its_own_part(tmp_path: Path) -> None:
    parts = write_judging_parts(_batch(2, 5_000), tmp_path, max_chars=1_000)
    assert len(parts) == 2


def test_parts_are_capped_by_response_count(tmp_path: Path) -> None:
    batch = {
        "timestamp": "20260101_000000",
        "pending_judgments": [
            {"prompt_id": index, "attempt": 0, "responses": {alias: "ok" for alias in "ABCDEFGHI"}}
            for index in range(5)
        ],
    }
    parts = write_judging_parts(batch, tmp_path, max_chars=1_000_000, max_responses=18)

    counts = [
        sum(len(item["responses"]) for item in json.loads(part.read_text())["pending_judgments"]) for part in parts
    ]
    assert counts == [18, 18, 9]

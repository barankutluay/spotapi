import json
import re
from pathlib import Path
from typing import Any, Dict, Generator
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console
from rich.table import Table

from album import AlbumError, PublicAlbum

# --------------------------------------------------------------------------------------
# Rich Console & Markdown Report
# --------------------------------------------------------------------------------------
console: Console = Console(record=True)
REPORT_PATH: Path = Path(f"./spotapi_tests/reports_{Path(__file__).stem}.md")
REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)


def save_report() -> None:
    console.save_text(str(REPORT_PATH))


def log_table(title: str, data: Dict[str, Any]) -> None:
    table: Table = Table(title=title)
    table.add_column("Metric", style="cyan", justify="left")
    table.add_column("Value", style="magenta", justify="right")
    for k, v in data.items():
        table.add_row(str(k), str(v))
    console.print(table)
    with REPORT_PATH.open("a", encoding="utf-8") as f:
        f.write(f"### {title}\n\n")
        f.write("| Metric | Value |\n|--------|-------|\n")
        for k, v in data.items():
            f.write(f"| {k} | {v} |\n")
        f.write("\n")


def log_message(msg: str) -> None:
    console.print(msg)
    with REPORT_PATH.open("a", encoding="utf-8") as f:
        clean: str = re.sub(r"\[.*?\]", "", msg)
        f.write(f"{clean}\n\n")


# --------------------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------------------
@pytest.fixture
def mock_client() -> Generator[MagicMock, None, None]:
    client = MagicMock()
    yield client


@pytest.fixture(scope="session", autouse=True)
def clear_report():
    if REPORT_PATH.exists():
        REPORT_PATH.unlink()
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    yield


# --------------------------------------------------------------------------------------
# Unit Tests
# --------------------------------------------------------------------------------------
def test_album_integration_flow() -> None:
    mock_tls_client = MagicMock()
    album = PublicAlbum("testid", client=mock_tls_client)

    mock_batch = [{"name": f"track{i}"} for i in range(10)]
    total_count = 10

    def fake_get_album_info(*args, **kwargs):
        return {
            "data": {
                "albumUnion": {
                    "tracksV2": {"totalCount": total_count, "items": mock_batch}
                }
            }
        }

    with patch.object(album.base, "part_hash", return_value="dummy_hash"), patch.object(
        PublicAlbum, "get_album_info", side_effect=fake_get_album_info
    ):
        info = album.get_album_info(limit=5)
        batches = list(album.paginate_album())

    log_table(
        "Integration Album Info",
        {"Tracks Count": len(info["data"]["albumUnion"]["tracksV2"]["items"])},
    )
    log_message(f"Integration pagination yielded {len(batches)} batch(es).")

    assert info["data"]["albumUnion"]["tracksV2"]["totalCount"] == total_count
    assert len(batches[0]) == 10


def test_public_album_initialization(mock_client: MagicMock) -> None:
    album = PublicAlbum("testid", client=mock_client)
    log_table(
        "Album Initialization",
        {
            "Album ID": album.album_id,
            "Album Link": album.album_link,
            "Base Client": type(album.base).__name__,
        },
    )
    assert album.album_id == "testid"
    assert album.album_link == "https://open.spotify.com/album/testid"
    assert album.base.client == mock_client


def test_build_album_query_structure(mock_client: MagicMock) -> None:
    album = PublicAlbum("testid", client=mock_client)
    with patch.object(album.base, "part_hash", return_value="dummy_hash"):
        query = album._build_album_query(limit=10, offset=0)
    log_table("Album Query Structure", {k: type(v).__name__ for k, v in query.items()})
    assert "operationName" in query
    assert "variables" in query
    assert "extensions" in query
    variables = json.loads(query["variables"])
    assert variables["uri"] == "spotify:album:testid"


def test_validate_response_accepts_mapping(mock_client: MagicMock) -> None:
    album = PublicAlbum("testid", client=mock_client)
    response = {"key": "value"}
    result = album._validate_response(response)
    assert result == response
    log_message("_validate_response accepted a valid mapping.")


def test_validate_response_raises_error(mock_client: MagicMock) -> None:
    album = PublicAlbum("testid", client=mock_client)
    with pytest.raises(AlbumError):
        album._validate_response("invalid_response")
    log_message("_validate_response raised AlbumError for invalid response.")


def test_get_album_info_success(mock_client: MagicMock) -> None:
    album = PublicAlbum("testid", client=mock_client)
    mock_resp = MagicMock()
    mock_resp.fail = False
    mock_resp.response = {
        "data": {"albumUnion": {"tracksV2": {"totalCount": 0, "items": []}}}
    }
    album.base.client.post.return_value = mock_resp

    with patch.object(album.base, "part_hash", return_value="dummy_hash"):
        result = album.get_album_info(limit=5)
    log_table(
        "Get Album Info",
        {"Tracks Count": len(result["data"]["albumUnion"]["tracksV2"]["items"])},
    )
    assert isinstance(result, dict)


def test_get_album_info_failure(mock_client: MagicMock) -> None:
    album = PublicAlbum("testid", client=mock_client)
    mock_resp = MagicMock()
    mock_resp.fail = True
    mock_resp.error.string = "failure"
    album.base.client.post.return_value = mock_resp

    with patch.object(album.base, "part_hash", return_value="dummy_hash"):
        with pytest.raises(AlbumError):
            album.get_album_info()
    log_message("get_album_info raised AlbumError on failure response.")


def test_paginate_album_yields_batches(mock_client: MagicMock) -> None:
    album = PublicAlbum("testid", client=mock_client)
    mock_batch = [{"name": f"track{i}"} for i in range(25)]
    total_count = 700

    def fake_get_album_info(limit, offset=0):
        items = mock_batch
        return {
            "data": {
                "albumUnion": {"tracksV2": {"totalCount": total_count, "items": items}}
            }
        }

    with patch.object(PublicAlbum, "get_album_info", side_effect=fake_get_album_info):
        batches = list(album.paginate_album())

    log_table("Paginate Album Batches", {"Number of Batches": len(batches)})
    assert len(batches) >= 2
    assert all(isinstance(batch, list) for batch in batches)

import json
import re
from pathlib import Path
from typing import Any, Dict, Generator
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console
from rich.table import Table

from artist import Artist, ArtistError

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
    yield MagicMock()


@pytest.fixture(scope="session", autouse=True)
def clear_report():
    if REPORT_PATH.exists():
        REPORT_PATH.unlink()
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    yield


# --------------------------------------------------------------------------------------
# Integration Test
# --------------------------------------------------------------------------------------
def test_artist_integration_flow() -> None:
    mock_client = MagicMock()
    artist = Artist(client=mock_client)

    mock_batch = [{"name": f"artist{i}"} for i in range(10)]
    total_count = 10

    def fake_query_artists(*args, **kwargs):
        return {
            "data": {
                "searchV2": {
                    "artists": {
                        "totalCount": total_count,
                        "items": mock_batch,
                    }
                }
            }
        }

    with patch.object(
        artist.base, "part_hash", return_value="dummy_hash"
    ), patch.object(Artist, "query_artists", side_effect=fake_query_artists):
        info = artist.query_artists("test query")
        batches = list(artist.paginate_artists("test query"))

    log_table(
        "Integration Artist Info",
        {"Artists Count": len(info["data"]["searchV2"]["artists"]["items"])},
    )
    log_message(f"Integration pagination yielded {len(batches)} batch(es).")

    assert info["data"]["searchV2"]["artists"]["totalCount"] == total_count
    assert len(batches[0]) == 10


# --------------------------------------------------------------------------------------
# Unit Tests
# --------------------------------------------------------------------------------------
def test_artist_initialization(mock_client: MagicMock) -> None:
    artist = Artist(client=mock_client)
    log_table(
        "Artist Initialization",
        {
            "Requires Login": artist._login,
            "Base Client": type(artist.base).__name__,
        },
    )
    assert artist._login is False
    assert artist.base.client == mock_client


def test_query_artists_success(mock_client: MagicMock) -> None:
    artist = Artist(client=mock_client)
    mock_resp = MagicMock()
    mock_resp.fail = False
    mock_resp.response = {
        "data": {"searchV2": {"artists": {"totalCount": 0, "items": []}}}
    }
    mock_client.post.return_value = mock_resp

    with patch.object(artist.base, "part_hash", return_value="dummy_hash"):
        result = artist.query_artists("test query", limit=5)
    log_table(
        "Query Artists",
        {"Artists Count": len(result["data"]["searchV2"]["artists"]["items"])},
    )
    assert isinstance(result, dict)


def test_query_artists_failure(mock_client: MagicMock) -> None:
    artist = Artist(client=mock_client)
    mock_resp = MagicMock()
    mock_resp.fail = True
    mock_resp.error.string = "error"
    mock_client.post.return_value = mock_resp

    with patch.object(artist.base, "part_hash", return_value="dummy_hash"):
        with pytest.raises(ArtistError):
            artist.query_artists("fail test")
    log_message("query_artists raised ArtistError on failure response.")


def test_get_artist_success(mock_client: MagicMock) -> None:
    artist = Artist(client=mock_client)
    mock_resp = MagicMock()
    mock_resp.fail = False
    mock_resp.response = {"data": {"artist": {"name": "Test Artist"}}}
    mock_client.get.return_value = mock_resp

    with patch.object(artist.base, "part_hash", return_value="dummy_hash"):
        result = artist.get_artist("artist:testid")
    log_table("Get Artist", {"Artist Name": result["data"]["artist"]["name"]})
    assert result["data"]["artist"]["name"] == "Test Artist"


def test_get_artist_failure(mock_client: MagicMock) -> None:
    artist = Artist(client=mock_client)
    mock_resp = MagicMock()
    mock_resp.fail = True
    mock_resp.error.string = "error"
    mock_client.get.return_value = mock_resp

    with patch.object(artist.base, "part_hash", return_value="dummy_hash"):
        with pytest.raises(ArtistError):
            artist.get_artist("failid")
    log_message("get_artist raised ArtistError on failure response.")


def test_paginate_artists(mock_client: MagicMock) -> None:
    artist = Artist(client=mock_client)
    mock_batch = [{"name": f"artist{i}"} for i in range(25)]
    total_count = 150

    def fake_query_artists(*args, **kwargs):
        offset = kwargs.get("offset", 0)
        return {
            "data": {
                "searchV2": {
                    "artists": {
                        "totalCount": total_count,
                        "items": mock_batch,
                    }
                }
            }
        }

    with patch.object(Artist, "query_artists", side_effect=fake_query_artists):
        batches = list(artist.paginate_artists("query"))

    log_table("Paginate Artists Batches", {"Number of Batches": len(batches)})
    assert len(batches) >= 2
    assert all(isinstance(batch, list) for batch in batches)


def test_follow_unfollow_methods(mock_client: MagicMock) -> None:
    artist = Artist(client=mock_client)
    artist._login = True

    # Mock post response
    mock_resp = MagicMock()
    mock_resp.fail = False
    mock_client.post.return_value = mock_resp

    with patch.object(artist.base, "part_hash", return_value="dummy_hash"):
        # Follow
        artist.follow("artist:testid")
        # Unfollow
        artist.unfollow("artist:testid")

    # Ensure post was called twice
    assert mock_client.post.call_count == 2
    log_message("Follow and unfollow methods executed successfully.")


def test_follow_without_login_raises(mock_client: MagicMock) -> None:
    artist = Artist(client=mock_client)
    artist._login = False

    with pytest.raises(ValueError):
        artist.follow("artist:testid")

    with pytest.raises(ValueError):
        artist.unfollow("artist:testid")

    log_message("Follow/unfollow raised ValueError when login required.")

from unittest.mock import MagicMock, patch

import pytest

from artist import Artist, ArtistError
from spotapi_tests.helpers import log_message, log_table


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


def test_artist_init_requires_login():
    mock_login = MagicMock()
    mock_login.logged_in = False
    with pytest.raises(ValueError):
        Artist(login=mock_login)


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


def test_query_artists_invalid_json(mock_client):
    artist = Artist(client=mock_client)
    mock_resp = MagicMock()
    mock_resp.fail = False
    mock_resp.response = "not a dict"
    mock_client.post.return_value = mock_resp
    with patch.object(artist.base, "part_hash", return_value="dummy_hash"):
        with pytest.raises(ArtistError):
            artist.query_artists("test")


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


def test_get_artist_invalid_json(mock_client):
    artist = Artist(client=mock_client)
    mock_resp = MagicMock()
    mock_resp.fail = False
    mock_resp.response = ["not a dict"]
    mock_client.get.return_value = mock_resp
    with patch.object(artist.base, "part_hash", return_value="dummy_hash"):
        with pytest.raises(ArtistError):
            artist.get_artist("artist:testid")


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


def test_paginate_artists_single_page(mock_client: MagicMock) -> None:
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

    with patch.object(Artist, "query_artists", side_effect=fake_query_artists):
        batches = list(artist.paginate_artists("query"))

    log_table("Paginate Artists Single Page", {"Batches": len(batches)})
    assert len(batches) == 1
    assert len(batches[0]) == 10


def test_paginate_artists_multiple_pages(mock_client: MagicMock) -> None:
    artist = Artist(client=mock_client)
    mock_batch = [{"name": f"artist{i}"} for i in range(50)]
    total_count = 150  # multiple pages

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

    log_table("Paginate Artists Multiple Pages", {"Number of Batches": len(batches)})
    assert len(batches) >= 2
    assert all(isinstance(batch, list) for batch in batches)


def test_do_follow_artist_prefix(mock_client: MagicMock) -> None:
    artist = Artist(client=mock_client)
    artist._login = True
    mock_resp = MagicMock()
    mock_resp.fail = False
    mock_client.post.return_value = mock_resp
    with patch.object(artist.base, "part_hash", return_value="dummy_hash"):
        artist._do_follow("artist:1234", action="addToLibrary")
        artist._do_follow("5678", action="addToLibrary")


def test_do_follow_success_and_fail(mock_client: MagicMock) -> None:
    artist = Artist(client=mock_client)
    artist._login = True
    mock_resp = MagicMock()
    mock_resp.fail = False
    mock_client.post.return_value = mock_resp

    with patch.object(artist.base, "part_hash", return_value="dummy_hash"):
        artist._do_follow("artist:testid", action="addToLibrary")
        artist._do_follow("artist:testid", action="removeFromLibrary")

    mock_resp.fail = True
    mock_resp.error.string = "error"
    with patch.object(artist.base, "part_hash", return_value="dummy_hash"):
        with pytest.raises(ArtistError):
            artist._do_follow("artist:testid", action="addToLibrary")
    log_message("_do_follow success and failure branches tested.")


def test_follow_unfollow_methods(mock_client: MagicMock) -> None:
    artist = Artist(client=mock_client)
    artist._login = True
    mock_resp = MagicMock()
    mock_resp.fail = False
    mock_client.post.return_value = mock_resp

    with patch.object(artist.base, "part_hash", return_value="dummy_hash"):
        artist.follow("artist:testid")
        artist.unfollow("artist:testid")

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

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Generator

from spotapi.client import BaseClient
from spotapi.spotapi_exceptions import AlbumError
from spotapi.spotapi_http.request import TLSClient
from spotapi.spotapi_types.annotations import enforce

__all__ = ["PublicAlbum", "AlbumError"]


@enforce
class PublicAlbum:
    """
    Fetches public information for a Spotify album.

    Attributes:
        base (BaseClient): Base client for sending HTTP requests.
        album_id (str): Spotify album ID.
        album_link (str): Public Spotify URL for the album.
    """

    DEFAULT_CLIENT = TLSClient("chrome_120", "", auto_retries=3)

    __slots__ = ("base", "album_id", "album_link")

    def __init__(self, album: str, /, *, client: TLSClient | None = None) -> None:
        """
        Initialize PublicAlbum instance.

        Args:
            album (str): Spotify album URI or album ID.
            client (TLSClient | None): Optional TLSClient instance. Defaults to DEFAULT_CLIENT.
        """
        self.base = BaseClient(client=client or self.DEFAULT_CLIENT)
        self.album_id = album.split("album/")[-1] if "album" in album else album
        self.album_link = f"https://open.spotify.com/album/{self.album_id}"

    def _build_album_query(self, limit: int, offset: int) -> dict[str, str]:
        """
        Build query parameters for album API request.

        Args:
            limit (int): Number of tracks to fetch.
            offset (int): Offset for pagination.

        Returns:
            dict[str, str]: Parameters for the POST request.
        """
        return {
            "operationName": "getAlbum",
            "variables": json.dumps(
                {
                    "locale": "",
                    "uri": f"spotify:album:{self.album_id}",
                    "offset": offset,
                    "limit": limit,
                }
            ),
            "extensions": json.dumps(
                {
                    "persistedQuery": {
                        "version": 1,
                        "sha256Hash": self.base.part_hash("getAlbum"),
                    }
                }
            ),
        }

    def _validate_response(self, response: Any) -> Mapping[str, Any]:
        """
        Validate the API response.

        Args:
            response (Any): API response object.

        Returns:
            Mapping[str, Any]: Validated response.

        Raises:
            AlbumError: If response is not a mapping.
        """
        if not isinstance(response, Mapping):
            raise AlbumError("Invalid JSON response")
        return response

    def get_album_info(self, limit: int = 25, *, offset: int = 0) -> Mapping[str, Any]:
        """
        Retrieve public album information.

        Args:
            limit (int, optional): Number of tracks to fetch per request. Defaults to 25.
            offset (int, optional): Track offset for pagination. Defaults to 0.

        Returns:
            Mapping[str, Any]: Album metadata and track info.

        Raises:
            AlbumError: If request fails.
        """
        url = "https://api-partner.spotify.com/pathfinder/v1/query"
        params = self._build_album_query(limit, offset)
        resp = self.base.client.post(url, params=params, authenticate=True)

        if resp.fail:
            raise AlbumError("Could not get album info", error=resp.error.string)

        return self._validate_response(resp.response)

    def paginate_album(self) -> Generator[list[Mapping[str, Any]], None, None]:
        """
        Generator that fetches album tracks in batches.

        Yields:
            list[Mapping[str, Any]]: Batch of track items.

        Raises:
            AlbumError: If initial request fails.
        """
        UPPER_LIMIT = 343
        album_data = self.get_album_info(limit=UPPER_LIMIT)
        tracks_v2 = album_data["data"]["albumUnion"]["tracksV2"]
        total_count = tracks_v2["totalCount"]

        yield tracks_v2["items"]

        for offset in range(UPPER_LIMIT, total_count, UPPER_LIMIT):
            batch = self.get_album_info(limit=UPPER_LIMIT, offset=offset)["data"][
                "albumUnion"
            ]["tracksV2"]["items"]
            yield batch

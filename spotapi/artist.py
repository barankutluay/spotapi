from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Generator, Literal, Optional

from spotapi.client import BaseClient
from spotapi.exceptions import ArtistError
from spotapi.http.request import TLSClient
from spotapi.login import Login
from spotapi.spotapitypes.annotations import enforce

__all__ = ["Artist", "ArtistError"]


@enforce
class Artist:
    """
    Represents an artist in the Spotify catalog.

    Provides methods to search, retrieve, follow, and unfollow artists.

    Attributes:
        _login (bool): Indicates if login is required for certain actions.
        base (BaseClient): Base client for sending API requests.
    """

    __slots__ = ("_login", "base")

    # API Endpoints
    SEARCH_URL: str = "https://api-partner.spotify.com/pathfinder/v1/query"
    ARTIST_OVERVIEW_URL: str = "https://api-partner.spotify.com/pathfinder/v1/query"

    def __init__(
        self,
        login: Optional[Login] = None,
        *,
        client: TLSClient = TLSClient("chrome_120", "", auto_retries=3),
    ) -> None:
        """
        Initialize an Artist object.

        Args:
            login (Optional[Login]): Logged-in Login object for authentication.
            client (TLSClient, optional): TLSClient for API requests. Defaults to Chrome 120.

        Raises:
            ValueError: If login is provided but not authenticated.
        """
        if login and not login.logged_in:
            raise ValueError("Must be logged in")

        self._login: bool = bool(login)
        self.base: BaseClient = BaseClient(client=login.client if login else client)

    def query_artists(
        self, query: str, /, limit: int = 10, *, offset: int = 0
    ) -> Mapping[str, Any]:
        """
        Search for artists in the Spotify catalog.

        Args:
            query (str): Search query string.
            limit (int, optional): Number of results to return. Defaults to 10.
            offset (int, optional): Result offset for pagination. Defaults to 0.

        Returns:
            Mapping[str, Any]: JSON response containing artist search results.

        Raises:
            ArtistError: If the request fails or an invalid response is received.
        """
        params = {
            "operationName": "searchArtists",
            "variables": json.dumps(
                {
                    "searchTerm": query,
                    "offset": offset,
                    "limit": limit,
                    "numberOfTopResults": 5,
                    "includeAudiobooks": True,
                    "includePreReleases": False,
                }
            ),
            "extensions": json.dumps(
                {
                    "persistedQuery": {
                        "version": 1,
                        "sha256Hash": self.base.part_hash("searchArtists"),
                    }
                }
            ),
        }

        resp = self.base.client.post(self.SEARCH_URL, params=params, authenticate=True)
        if resp.fail:
            raise ArtistError("Could not get artists", error=resp.error.string)
        if not isinstance(resp.response, Mapping):
            raise ArtistError("Invalid JSON")

        return resp.response

    def get_artist(
        self, artist_id: str, /, *, locale_code: str = "en"
    ) -> Mapping[str, Any]:
        """
        Retrieve detailed information for a specific artist by ID.

        Args:
            artist_id (str): Spotify artist ID (with or without 'artist:' prefix).
            locale_code (str, optional): Locale code for returned content. Defaults to "en".

        Returns:
            Mapping[str, Any]: JSON response containing artist details.

        Raises:
            ArtistError: If request fails or invalid response is returned.
        """
        if "artist:" in artist_id:
            artist_id = artist_id.split("artist:")[-1]

        params = {
            "operationName": "queryArtistOverview",
            "variables": json.dumps(
                {
                    "uri": f"spotify:artist:{artist_id}",
                    "locale": locale_code,
                }
            ),
            "extensions": json.dumps(
                {
                    "persistedQuery": {
                        "version": 1,
                        "sha256Hash": self.base.part_hash("queryArtistOverview"),
                    }
                }
            ),
        }

        resp = self.base.client.get(
            self.ARTIST_OVERVIEW_URL, params=params, authenticate=True
        )
        if resp.fail:
            raise ArtistError("Could not get artist by ID", error=resp.error.string)
        if not isinstance(resp.response, Mapping):
            raise ArtistError("Invalid JSON response")

        return resp.response

    def paginate_artists(
        self, query: str, /
    ) -> Generator[Mapping[str, Any], None, None]:
        """
        Generator to fetch artists in chunks, useful for pagination.

        Args:
            query (str): Search query string.

        Yields:
            Mapping[str, Any]: JSON chunks of artists.

        Note:
            If total_count <= 100, pagination is not performed.
        """
        UPPER_LIMIT: int = 100
        artists = self.query_artists(query, limit=UPPER_LIMIT)
        total_count: int = artists["data"]["searchV2"]["artists"]["totalCount"]

        yield artists["data"]["searchV2"]["artists"]["items"]

        if total_count <= UPPER_LIMIT:
            return

        offset = UPPER_LIMIT
        while offset < total_count:
            chunk = self.query_artists(query, limit=UPPER_LIMIT, offset=offset)
            yield chunk["data"]["searchV2"]["artists"]["items"]
            offset += UPPER_LIMIT

    def _do_follow(
        self,
        artist_id: str,
        /,
        *,
        action: Literal["addToLibrary", "removeFromLibrary"] = "addToLibrary",
    ) -> None:
        """
        Internal method to follow or unfollow an artist.

        Args:
            artist_id (str): Spotify artist ID.
            action (Literal): Action to perform, either "addToLibrary" or "removeFromLibrary".

        Raises:
            ValueError: If not logged in.
            ArtistError: If the request fails.
        """
        if not self._login:
            raise ValueError("Must be logged in")

        if "artist:" in artist_id:
            artist_id = artist_id.split("artist:")[-1]

        payload = {
            "variables": {"uris": [f"spotify:artist:{artist_id}"]},
            "operationName": action,
            "extensions": {
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": self.base.part_hash(str(action)),
                }
            },
        }

        resp = self.base.client.post(self.SEARCH_URL, json=payload, authenticate=True)
        if resp.fail:
            raise ArtistError(
                f"Could not {action.replace('ToLibrary', '')} artist",
                error=resp.error.string,
            )

    def follow(self, artist_id: str, /) -> None:
        """
        Follow an artist by ID.

        Args:
            artist_id (str): Spotify artist ID.
        """
        self._do_follow(artist_id)

    def unfollow(self, artist_id: str, /) -> None:
        """
        Unfollow an artist by ID.

        Args:
            artist_id (str): Spotify artist ID.
        """
        self._do_follow(artist_id, action="removeFromLibrary")

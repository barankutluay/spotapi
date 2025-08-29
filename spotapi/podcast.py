from __future__ import annotations

import json
from collections.abc import Generator, Mapping
from typing import Any

from spotapi.client import BaseClient
from spotapi.spotapi_exceptions import PodcastError
from spotapi.spotapi_http.request import TLSClient
from spotapi.spotapi_types.annotations import enforce

__all__ = ["Podcast", "PodcastError"]


@enforce
class Podcast:
    """
    Provides access to public information about a Spotify podcast and its episodes.

    Args:
        podcast (str | None): The Spotify URI of the podcast.
        client (TLSClient, optional): HTTP client to use for requests. Defaults to a TLSClient instance.
    """

    __slots__ = (
        "base",
        "podcast_link",
        "podcast_id",
    )

    def __init__(
        self,
        podcast: str | None = None,
        *,
        client: TLSClient = TLSClient("chrome_120", "", auto_retries=3),
    ) -> None:
        """
        Initializes a Podcast instance.

        Args:
            podcast (str | None): Spotify URI of the podcast.
            client (TLSClient, optional): HTTP client for requests. Defaults to a TLSClient instance.
        """
        self.base = BaseClient(client=client)
        if podcast:
            self.podcast_id = self._extract_podcast_id(podcast)
            self.podcast_link = f"https://open.spotify.com/show/{self.podcast_id}"

    @staticmethod
    def _extract_podcast_id(podcast: str) -> str:
        """
        Extracts the podcast ID from a Spotify URI or URL.

        Args:
            podcast (str): Spotify URI or ID of the podcast.

        Returns:
            str: The extracted podcast ID.
        """
        return podcast.split("show/")[-1] if "show" in podcast else podcast

    def _send_request(
        self, operation: str, variables: dict[str, Any]
    ) -> Mapping[str, Any]:
        """
        Send a request to the Spotify API and validate the response.

        Args:
            operation (str): API operation name.
            variables (dict[str, Any]): Request variables.

        Returns:
            Mapping[str, Any]: Parsed JSON response.

        Raises:
            PodcastError: If the request fails or the response is invalid.
        """
        url = "https://api-partner.spotify.com/pathfinder/v1/query"
        params = {
            "operationName": operation,
            "variables": json.dumps(variables),
            "extensions": json.dumps(
                {
                    "persistedQuery": {
                        "version": 1,
                        "sha256Hash": self.base.part_hash(operation),
                    }
                }
            ),
        }

        resp = self.base.client.post(url, params=params, authenticate=True)
        if resp.fail:
            raise PodcastError(
                f"Could not execute operation {operation}", error=resp.error.string
            )

        if not isinstance(resp.response, Mapping):
            raise PodcastError("Invalid JSON response")

        return resp.response

    def get_episode(self, episode_id: str) -> Mapping[str, Any]:
        """
        Retrieve information for a specific episode.

        Args:
            episode_id (str): Spotify episode ID.

        Returns:
            Mapping[str, Any]: Episode information.

        Raises:
            PodcastError: If the request fails or the response is invalid.
        """
        return self._send_request(
            "getEpisodeOrChapter", {"uri": f"spotify:episode:{episode_id}"}
        )

    def get_podcast_info(
        self, limit: int = 25, *, offset: int = 0
    ) -> Mapping[str, Any]:
        """
        Retrieve public information about the podcast and its episodes.

        Args:
            limit (int, optional): Number of episodes to retrieve. Defaults to 25.
            offset (int, optional): Pagination offset. Defaults to 0.

        Returns:
            Mapping[str, Any]: Podcast information.

        Raises:
            PodcastError: If Podcast ID is not set, request fails, or response is invalid.
        """
        if not hasattr(self, "podcast_id"):
            raise PodcastError("Podcast ID must be set")

        variables = {
            "uri": f"spotify:show:{self.podcast_id}",
            "offset": offset,
            "limit": limit,
        }
        return self._send_request("queryPodcastEpisodes", variables)

    def paginate_podcast(self) -> Generator[Mapping[str, Any], None, None]:
        """
        Generator that fetches podcast episodes in chunks (pagination).

        Yields:
            Generator[Mapping[str, Any], None, None]: Podcast episodes in chunks.

        Raises:
            PodcastError: If request fails or response is invalid.
        """
        UPPER_LIMIT: int = 343
        podcast = self.get_podcast_info(limit=UPPER_LIMIT)
        total_count: int = podcast["data"]["podcastUnionV2"]["episodesV2"]["totalCount"]

        yield podcast["data"]["podcastUnionV2"]["episodesV2"]["items"]

        if total_count <= UPPER_LIMIT:
            return

        offset = UPPER_LIMIT
        while offset < total_count:
            data = self.get_podcast_info(limit=UPPER_LIMIT, offset=offset)["data"][
                "podcastUnionV2"
            ]["episodesV2"]["items"]
            yield data
            offset += UPPER_LIMIT

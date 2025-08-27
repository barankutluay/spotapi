from __future__ import annotations

import json
import re
import time
from collections.abc import Mapping
from typing import Any, Generator, Mapping, Optional

from spotapi.client import BaseClient
from spotapi.exceptions import PlaylistError
from spotapi.http.request import TLSClient
from spotapi.login import Login
from spotapi.spotapitypes.annotations import enforce
from spotapi.user import User

__all__ = ["PublicPlaylist", "PrivatePlaylist", "PlaylistError"]


@enforce
class PublicPlaylist:
    """
    Provides methods to fetch public playlist information without authentication.

    Attributes:
        base (BaseClient): Base client for HTTP requests.
        playlist_id (str): Spotify playlist ID.
        playlist_link (str): Full Spotify playlist URL.
    """

    __slots__ = ("base", "playlist_id", "playlist_link")

    def __init__(
        self,
        playlist: str,
        /,
        *,
        client: TLSClient = TLSClient("chrome_120", "", auto_retries=3),
    ) -> None:
        self.base = BaseClient(client=client)
        self.playlist_id = self._extract_playlist_id(playlist)
        self.playlist_link = f"https://open.spotify.com/playlist/{self.playlist_id}"

    @staticmethod
    def _extract_playlist_id(uri: str) -> str:
        return uri.split("playlist/")[-1] if "playlist" in uri else uri

    def get_playlist_info(
        self,
        limit: int = 25,
        *,
        offset: int = 0,
        enable_watch_feed_entrypoint: bool = False,
    ) -> Mapping[str, Any]:
        """
        Fetches playlist information from Spotify public API.

        Args:
            limit (int): Maximum number of tracks to fetch.
            offset (int): Offset for pagination.
            enable_watch_feed_entrypoint (bool): Feature flag for watch feed.

        Returns:
            Mapping[str, Any]: JSON response containing playlist data.

        Raises:
            PlaylistError: If request fails or invalid response is returned.
        """
        url = "https://api-partner.spotify.com/pathfinder/v1/query"
        params = {
            "operationName": "fetchPlaylist",
            "variables": json.dumps(
                {
                    "uri": f"spotify:playlist:{self.playlist_id}",
                    "offset": offset,
                    "limit": limit,
                    "enableWatchFeedEntrypoint": enable_watch_feed_entrypoint,
                }
            ),
            "extensions": json.dumps(
                {
                    "persistedQuery": {
                        "version": 1,
                        "sha256Hash": self.base.part_hash("fetchPlaylist"),
                    }
                }
            ),
        }

        resp = self.base.client.post(url, params=params, authenticate=True)
        if resp.fail or not isinstance(resp.response, Mapping):
            raise PlaylistError(
                "Could not get playlist info", error=getattr(resp.error, "string", None)
            )
        return resp.response

    def paginate_playlist(self) -> Generator[Mapping[str, Any], None, None]:
        """
        Generator to fetch playlist tracks in chunks.

        Yields:
            Mapping[str, Any]: Chunk of playlist tracks.
        """
        UPPER_LIMIT = 343
        playlist_data = self.get_playlist_info(limit=UPPER_LIMIT)
        content = playlist_data["data"]["playlistV2"]["content"]
        total_count = content["totalCount"]

        yield content
        offset = UPPER_LIMIT
        while offset < total_count:
            chunk = self.get_playlist_info(limit=UPPER_LIMIT, offset=offset)["data"][
                "playlistV2"
            ]["content"]
            yield chunk
            offset += UPPER_LIMIT


@enforce
class PrivatePlaylist:
    """
    Provides methods to manage private playlists for logged-in users.

    Attributes:
        login (Login): Authenticated login instance.
        user (User): User instance linked to the login.
        base (BaseClient): Base client for HTTP requests.
        playlist_id (str | None): Spotify playlist ID.
    """

    __slots__ = ("base", "login", "user", "_playlist", "playlist_id")

    def __init__(self, login: Login, playlist: Optional[str] = None) -> None:
        if not login.logged_in:
            raise ValueError("Must be logged in")

        self.login = login
        self.user = User(login)
        self.base = BaseClient(login.client)

        self.playlist_id: Optional[str] = (
            self._extract_playlist_id(playlist) if playlist else None
        )
        self._playlist = bool(playlist)

    @staticmethod
    def _extract_playlist_id(uri: str) -> str:
        return uri.split("playlist/")[-1] if uri and "playlist" in uri else uri

    def set_playlist(self, playlist: str) -> None:
        """Sets the active playlist for future operations."""
        playlist_id = self._extract_playlist_id(playlist)
        if not playlist_id:
            raise ValueError("Playlist not set")
        self.playlist_id = playlist_id
        self._playlist = True

    def _send_library_change(self, kind: int) -> None:
        """Sends add/remove playlist requests to Spotify."""
        if not self._playlist:
            raise ValueError("Playlist not set")

        url = f"https://spclient.wg.spotify.com/playlist/v2/user/{self.user.username}/rootlist/changes"
        payload = {
            "deltas": [
                {
                    "ops": [
                        {
                            "kind": kind,
                            "add" if kind == 2 else "rem": {
                                "items": [
                                    {
                                        "uri": f"spotify:playlist:{self.playlist_id}",
                                        "attributes": {
                                            "timestamp": int(time.time()),
                                            "formatAttributes": [],
                                            "availableSignals": [],
                                        },
                                    }
                                ],
                                "addFirst": True if kind == 2 else None,
                                "itemsAsKey": True if kind == 3 else None,
                            },
                        }
                    ],
                    "info": {"source": {"client": 5}},
                }
            ],
            "wantResultingRevisions": False,
            "wantSyncResult": False,
            "nonces": [],
        }

        resp = self.login.client.post(url, json=payload, authenticate=True)
        if resp.fail:
            action = "add" if kind == 2 else "remove"
            raise PlaylistError(
                f"Could not {action} playlist to library",
                error=getattr(resp.error, "string", None),
            )

    def add_to_library(self) -> None:
        """Adds the playlist to the user's library."""
        self._send_library_change(kind=2)

    def remove_from_library(self) -> None:
        """Removes the playlist from the user's library."""
        self._send_library_change(kind=3)

    def delete_playlist(self) -> None:
        """Alias for remove_from_library."""
        self.remove_from_library()

    def get_library(self, limit: int = 50) -> Mapping[str, Any]:
        """
        Retrieves the user's library playlists.

        Args:
            limit (int): Max number of playlists to fetch.

        Returns:
            Mapping[str, Any]: Library JSON response.

        Raises:
            PlaylistError: If request fails.
        """
        url = "https://api-partner.spotify.com/pathfinder/v1/query"
        params = {
            "operationName": "libraryV3",
            "variables": json.dumps(
                {
                    "filters": [],
                    "order": None,
                    "textFilter": "",
                    "features": ["LIKED_SONGS", "YOUR_EPISODES", "PRERELEASES"],
                    "limit": limit,
                    "offset": 0,
                    "flatten": False,
                    "expandedFolders": [],
                    "folderUri": None,
                    "includeFoldersWhenFlattening": True,
                }
            ),
            "extensions": json.dumps(
                {
                    "persistedQuery": {
                        "version": 1,
                        "sha256Hash": self.base.part_hash("libraryV3"),
                    }
                }
            ),
        }

        resp = self.login.client.post(url, params=params, authenticate=True)
        if resp.fail:
            raise PlaylistError(
                "Could not get library", error=getattr(resp.error, "string", None)
            )
        return resp.response

    def _stage_create_playlist(self, name: str) -> str:
        """Stages creation of a playlist and returns its Spotify URI."""
        url = "https://spclient.wg.spotify.com/playlist/v2/playlist"
        payload = {
            "ops": [
                {
                    "kind": 6,
                    "updateListAttributes": {
                        "newAttributes": {
                            "values": {
                                "name": name,
                                "formatAttributes": [],
                                "pictureSize": [],
                            },
                            "noValue": [],
                        }
                    },
                }
            ]
        }

        resp = self.login.client.post(url, json=payload, authenticate=True)
        if resp.fail:
            raise PlaylistError(
                "Could not stage create playlist",
                error=getattr(resp.error, "string", None),
            )

        match = re.search(r"spotify:playlist:[a-zA-Z0-9]+", resp.response)
        if not match:
            raise PlaylistError("Could not find desired playlist ID")
        return match.group(0)

    def create_playlist(self, name: str) -> str:
        """
        Creates a new playlist and adds it to the user's library.

        Args:
            name (str): Name of the new playlist.

        Returns:
            str: Spotify URI of the new playlist.
        """
        playlist_id = self._stage_create_playlist(name)
        self._send_library_change(kind=2)
        return playlist_id

    def recommended_songs(self, num_songs: int = 20) -> Mapping[str, Any]:
        """
        Retrieves recommended songs for the playlist.

        Args:
            num_songs (int): Number of songs to fetch.

        Returns:
            Mapping[str, Any]: JSON response of recommended songs.

        Raises:
            PlaylistError: If request fails.
        """
        if not self._playlist:
            raise ValueError("Playlist not set")

        url = "https://spclient.wg.spotify.com/playlistextender/extendp/"
        payload = {
            "playlistURI": f"spotify:playlist:{self.playlist_id}",
            "trackSkipIDs": [],
            "numResults": num_songs,
        }
        resp = self.login.client.post(url, json=payload, authenticate=True)
        if resp.fail:
            raise PlaylistError(
                "Could not get recommended songs",
                error=getattr(resp.error, "string", None),
            )
        return resp.response

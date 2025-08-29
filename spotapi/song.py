import json
from typing import Any, Generator, Iterable, List, Mapping, Optional, Tuple

from spotapi.client import BaseClient
from spotapi.playlist import PrivatePlaylist, PublicPlaylist
from spotapi.spotapi_exceptions import SongError
from spotapi.spotapi_http.request import TLSClient
from spotapi.spotapi_types.annotations import enforce

__all__ = ["Song", "SongError"]


@enforce
class Song:
    """
    Handles Spotify song operations within the context of a playlist.

    This class allows searching songs, retrieving track information, adding/removing
    songs from playlists, and liking songs. It requires a playlist instance for operations
    that modify a playlist.

    Args:
        playlist (Optional[PrivatePlaylist]): Playlist context for modifications.
        client (Optional[TLSClient]): HTTP client instance if no playlist is provided.
    """

    __slots__ = ("playlist", "base")

    def __init__(
        self,
        playlist: Optional[PrivatePlaylist] = None,
        *,
        client: TLSClient = TLSClient("chrome_120", "", auto_retries=3),
    ) -> None:
        self.playlist = playlist
        self.base = BaseClient(client=playlist.login.client if playlist else client)

    def _send_post(
        self, operation: str, variables: dict[str, Any]
    ) -> Mapping[str, Any]:
        """
        Sends a POST request to Spotify's PathFinder API and validates response.

        Args:
            operation (str): API operation name.
            variables (dict[str, Any]): Request variables.

        Returns:
            Mapping[str, Any]: JSON response.

        Raises:
            SongError: If request fails or response is invalid.
        """
        url = "https://api-partner.spotify.com/pathfinder/v1/query"
        payload = {
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

        resp = self.base.client.post(url, json=payload, authenticate=True)
        if resp.fail:
            raise SongError(
                f"Could not execute operation {operation}", error=resp.error.string
            )

        if not isinstance(resp.response, Mapping):
            raise SongError("Invalid JSON response")

        return resp.response

    def get_track_info(self, track_id: str) -> Mapping[str, Any]:
        """
        Retrieves information for a specific track.

        Args:
            track_id (str): Spotify track ID.

        Returns:
            Mapping[str, Any]: Track information.

        Raises:
            SongError: If request fails or response is invalid.
        """
        return self._send_post("getTrack", {"uri": f"spotify:track:{track_id}"})

    def query_songs(
        self, query: str, limit: int = 10, *, offset: int = 0
    ) -> Mapping[str, Any]:
        """
        Searches for songs in Spotify's catalog.

        Args:
            query (str): Search query.
            limit (int, optional): Maximum number of results to fetch. Defaults to 10.
            offset (int, optional): Pagination offset. Defaults to 0.

        Returns:
            Mapping[str, Any]: Raw search result.

        Raises:
            SongError: If request fails or response is invalid.
        """
        variables = {
            "searchTerm": query,
            "offset": offset,
            "limit": limit,
            "numberOfTopResults": 5,
            "includeAudiobooks": True,
            "includeArtistHasConcertsField": False,
            "includePreReleases": True,
            "includeLocalConcertsField": False,
        }
        return self._send_post("searchDesktop", variables)

    def paginate_songs(
        self, query: str
    ) -> Generator[List[Mapping[str, Any]], None, None]:
        """
        Generator that yields search results in chunks.

        Args:
            query (str): Search query.

        Yields:
            List[Mapping[str, Any]]: Chunk of song items.

        Raises:
            SongError: If request fails or response is invalid.
        """
        UPPER_LIMIT = 100
        songs = self.query_songs(query, limit=UPPER_LIMIT)
        total_count: int = songs["data"]["searchV2"]["tracksV2"]["totalCount"]

        yield songs["data"]["searchV2"]["tracksV2"]["items"]

        offset = UPPER_LIMIT
        while offset < total_count:
            chunk = self.query_songs(query, limit=UPPER_LIMIT, offset=offset)["data"][
                "searchV2"
            ]["tracksV2"]["items"]
            yield chunk
            offset += UPPER_LIMIT

    def add_songs_to_playlist(self, song_ids: List[str]) -> None:
        """
        Adds multiple songs to the playlist.

        Args:
            song_ids (List[str]): List of Spotify track IDs.

        Raises:
            ValueError: If playlist is not set.
            SongError: If request fails.
        """
        if not self.playlist or not hasattr(self.playlist, "playlist_id"):
            raise ValueError("Playlist not set")

        variables = {
            "uris": [f"spotify:track:{song_id}" for song_id in song_ids],
            "playlistUri": f"spotify:playlist:{self.playlist.playlist_id}",
            "newPosition": {"moveType": "BOTTOM_OF_PLAYLIST", "fromUid": None},
        }
        self._send_post("addToPlaylist", variables)

    def add_song_to_playlist(self, song_id: str) -> None:
        """
        Adds a single song to the playlist.

        Args:
            song_id (str): Spotify track ID.
        """
        if "track" in song_id:
            song_id = song_id.split("track/")[-1]
        self.add_songs_to_playlist([song_id])

    def _stage_remove_song(self, uids: List[str]) -> None:
        """
        Removes songs from playlist by UID.

        Args:
            uids (List[str]): List of UIDs to remove.

        Raises:
            SongError: If request fails.
        """
        assert self.playlist is not None, "Playlist not set"
        variables = {
            "playlistUri": f"spotify:playlist:{self.playlist.playlist_id}",
            "uids": uids,
        }
        self._send_post("removeFromPlaylist", variables)

    @staticmethod
    def parse_playlist_items(
        items: Iterable[Mapping[str, Any]],
        song_id: Optional[str] = None,
        song_name: Optional[str] = None,
        all_instances: bool = False,
    ) -> Tuple[List[str], bool]:
        """
        Finds UIDs of songs in playlist items.

        Args:
            items (Iterable[Mapping[str, Any]]): Playlist items.
            song_id (Optional[str]): Spotify track ID to match.
            song_name (Optional[str]): Song name to match.
            all_instances (bool): Whether to return only the first match or all matches.

        Returns:
            Tuple[List[str], bool]: List of UIDs and a flag indicating stop condition.
        """
        uids: List[str] = []
        for item in items:
            matches_id = song_id and song_id in item["itemV2"]["data"]["uri"]
            matches_name = (
                song_name
                and song_name.lower() in str(item["itemV2"]["data"]["name"]).lower()
            )

            if matches_id or matches_name:
                uids.append(item["uid"])
                if not all_instances:
                    return uids, True

        return uids, False

    def remove_song_from_playlist(
        self,
        *,
        all_instances: bool = False,
        uid: Optional[str] = None,
        song_id: Optional[str] = None,
        song_name: Optional[str] = None,
    ) -> None:
        """
        Removes a song from the playlist.

        Args:
            all_instances (bool): Remove all instances of the song by name.
            uid (Optional[str]): UID of the song to remove.
            song_id (Optional[str]): Spotify track ID.
            song_name (Optional[str]): Name of the song.

        Raises:
            ValueError: If playlist not set or invalid parameters.
            SongError: If song not found or removal fails.
        """
        if song_id and "track" in song_id:
            song_id = song_id.split("track:")[-1]

        if not (song_id or song_name or uid):
            raise ValueError("Must provide either song_id, song_name, or uid")
        if all_instances and song_id:
            raise ValueError("Cannot provide both song_id and all_instances")
        if not self.playlist or not hasattr(self.playlist, "playlist_id"):
            raise ValueError("Playlist not set")

        playlist_gen = PublicPlaylist(self.playlist.playlist_id).paginate_playlist()
        uids: List[str] = []

        if not uid:
            for chunk in playlist_gen:
                items = chunk["items"]
                found_uids, stop = Song.parse_playlist_items(
                    items, song_id, song_name, all_instances
                )
                uids.extend(found_uids)
                if stop:
                    break
        else:
            uids.append(uid)

        if not uids:
            raise SongError("Song not found in playlist")

        self._stage_remove_song(uids)

    def like_song(self, song_id: str) -> None:
        """
        Likes a song (adds to library).

        Args:
            song_id (str): Spotify track ID.

        Raises:
            ValueError: If playlist is not set.
            SongError: If request fails.
        """
        if not self.playlist or not hasattr(self.playlist, "playlist_id"):
            raise ValueError("Playlist not set")
        if "track" in song_id:
            song_id = song_id.split("track:")[-1]

        self._send_post("addToLibrary", {"uris": [f"spotify:track:{song_id}"]})

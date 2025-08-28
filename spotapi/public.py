from collections import deque
from threading import Lock
from typing import (
    Any,
    Callable,
    Deque,
    Generator,
    Generic,
    Mapping,
    Optional,
    TypeAlias,
    TypeVar,
)

import spotapi
from spotapi.client import TLSClient

T = TypeVar("T")
GeneratorType: TypeAlias = Generator[Mapping[str, Any], None, None]


class Pooler(Generic[T]):
    """A thread-safe generic object pool for caching and reusing objects."""

    def __init__(
        self, factory: Callable[..., T], *, max_cache: Optional[int] = None
    ) -> None:
        """
        Args:
            factory: Callable that creates a new object if pool is empty.
            max_cache: Maximum number of objects to cache. Defaults to None (unbounded).
        """
        self._factory: Callable[..., T] = factory
        self._queue: Deque[T] = deque(maxlen=max_cache)
        self._lock = Lock()

    def get(self) -> T:
        """Retrieve an object from the pool or create a new one if pool is empty."""
        with self._lock:
            if self._queue:
                return self._queue.popleft()
            return self._factory()

    def put(self, obj: T) -> None:
        """Return an object to the pool."""
        with self._lock:
            self._queue.append(obj)

    def clear(self) -> None:
        """Clear all cached objects."""
        with self._lock:
            self._queue.clear()


# Global TLSClient pool
client_pool: Pooler[TLSClient] = Pooler(
    factory=lambda: TLSClient("chrome_120", "", auto_retries=3)
)


class ClientContext:
    """Context manager for safely acquiring and releasing a TLSClient from the pool."""

    def __enter__(self) -> TLSClient:
        self._client = client_pool.get()
        return self._client

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        client_pool.put(self._client)


class Public:
    """Access public Spotify data via Artist, Album, Playlist, Song, and Podcast APIs."""

    @staticmethod
    def artist_search(query: str) -> GeneratorType:
        """Search for artists by query string.

        Args:
            query: Search query for artist names.

        Yields:
            Mapping[str, Any]: Artist information in pages.
        """
        with ClientContext() as client:
            artist = spotapi.Artist(client=client)
            yield from artist.paginate_artists(query)

    @staticmethod
    def album_info(album_id: str) -> GeneratorType:
        """Retrieve album information by album ID.

        Args:
            album_id: Spotify album ID.

        Yields:
            Mapping[str, Any]: Album tracks in pages.
        """
        with ClientContext() as client:
            album = spotapi.PublicAlbum(album_id, client=client)
            yield from album.paginate_album()

    @staticmethod
    def playlist_info(playlist_id: str) -> GeneratorType:
        """Retrieve playlist information by playlist ID.

        Args:
            playlist_id: Spotify playlist ID.

        Yields:
            Mapping[str, Any]: Playlist tracks in pages.
        """
        with ClientContext() as client:
            playlist = spotapi.PublicPlaylist(playlist_id, client=client)
            yield from playlist.paginate_playlist()

    @staticmethod
    def song_search(query: str) -> GeneratorType:
        """Search for songs by query string.

        Args:
            query: Search query for songs.

        Yields:
            Mapping[str, Any]: Song information in pages.
        """
        with ClientContext() as client:
            song = spotapi.Song(client=client)
            yield from song.paginate_songs(query)

    @staticmethod
    def song_info(song_id: str) -> Mapping[str, Any]:
        """Retrieve information for a specific song by ID.

        Args:
            song_id: Spotify song ID.

        Returns:
            Mapping[str, Any]: Song details.
        """
        with ClientContext() as client:
            song = spotapi.Song(client=client)
            return song.get_track_info(song_id)

    @staticmethod
    def podcast_info(podcast_id: str) -> GeneratorType:
        """Retrieve podcast episodes by podcast ID.

        Args:
            podcast_id: Spotify podcast ID.

        Yields:
            Mapping[str, Any]: Podcast episodes in pages.
        """
        with ClientContext() as client:
            podcast = spotapi.Podcast(podcast_id, client=client)
            yield from podcast.paginate_podcast()

    @staticmethod
    def podcast_episode_info(episode_id: str) -> Mapping[str, Any]:
        """Retrieve information for a specific podcast episode.

        Args:
            episode_id: Spotify episode ID.

        Returns:
            Mapping[str, Any]: Episode details.
        """
        with ClientContext() as client:
            podcast = spotapi.Podcast(client=client)
            return podcast.get_episode(episode_id)

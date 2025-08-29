import functools
import threading
from typing import Any, Callable, Dict, List, Optional, ParamSpec, TypeVar

from spotapi.login import Login
from spotapi.spotapi_types.annotations import enforce
from spotapi.spotapi_types.data import Devices, PlayerState, Track
from spotapi.websocket import WebsocketStreamer

__all__ = [
    "PlayerStatus",
    "WebsocketStreamer",
    "EventManager",
    "PlayerState",
    "Devices",
    "Track",
]

R = TypeVar("R")
P = ParamSpec("P")


@enforce
class PlayerStatus(WebsocketStreamer):
    """
    Represents the current state of the Spotify player.

    Args:
        login (Login): The login instance for authentication.
        s_device_id (Optional[str]): Optional device ID to use. If None, a new device ID is generated.
    """

    _device_dump: Optional[Dict[str, Any]] = None
    _state: Optional[Dict[str, Any]] = None
    _devices: Optional[Dict[str, Any]] = None

    def __init__(self, login: Login, s_device_id: Optional[str] = None) -> None:
        super().__init__(login)
        if s_device_id:
            self.device_id = s_device_id

        self.register_device()

    def renew_state(self) -> None:
        """
        Refresh the player state and device information.
        """
        self._device_dump = self.connect_device()
        self._state = self._device_dump["player_state"]
        self._devices = self._device_dump["devices"]

    @functools.cached_property
    def saved_state(self) -> PlayerState:
        """
        Returns the last saved player state.

        Returns:
            PlayerState: Last saved player state.

        Raises:
            ValueError: If player state cannot be obtained.
        """
        if self._state is None:
            self.renew_state()

        if self._state is None:
            raise ValueError("Could not get player state")

        return PlayerState.from_dict(self._state)

    @property
    def state(self) -> PlayerState:
        """
        Returns the current player state.

        Returns:
            PlayerState: Current player state.

        Raises:
            ValueError: If player state cannot be obtained.
        """
        self.renew_state()
        if self._state is None:
            raise ValueError("Could not get player state")
        return PlayerState.from_dict(self._state)

    @functools.cached_property
    def saved_device_ids(self) -> Devices:
        """
        Returns the last saved device IDs.

        Returns:
            Devices: Last saved device information.

        Raises:
            ValueError: If devices cannot be obtained.
        """
        if self._devices is None:
            self.renew_state()

        if self._devices is None or self._device_dump is None:
            raise ValueError("Could not get devices or active device ID")

        return Devices.from_dict(self._devices, self._device_dump["active_device_id"])

    @property
    def device_ids(self) -> Devices:
        """
        Returns the current device IDs.

        Returns:
            Devices: Current devices.

        Raises:
            ValueError: If devices cannot be obtained.
        """
        self.renew_state()

        if self._devices is None:
            raise ValueError("Could not get devices")

        active_device_id = (
            self._device_dump.get("active_device_id") if self._device_dump else None
        )

        return Devices.from_dict(
            self._devices,
            str(active_device_id) if hasattr(active_device_id, "__str__") else None,  # type: ignore
        )

    @property
    def active_device_id(self) -> str:
        """
        Returns the active device ID.

        Returns:
            str: Active device ID.

        Raises:
            ValueError: If active device ID cannot be obtained.
        """
        self.renew_state()

        if (
            self._device_dump is None
            or self._device_dump.get("active_device_id") is None
        ):
            raise ValueError("Could not get active device ID")

        return self._device_dump["active_device_id"]

    @property
    def next_song_in_queue(self) -> Optional[Track]:
        """
        Returns the next track in the playback queue.

        Returns:
            Optional[Track]: Next track, or None if queue is empty.
        """
        state = self.state
        return state.next_tracks[0] if state.next_tracks else None

    @property
    def next_songs_in_queue(self) -> List[Track]:
        """
        Returns the upcoming tracks in the playback queue.

        Returns:
            List[Track]: Upcoming tracks.
        """
        return self.state.next_tracks

    @property
    def last_played(self) -> Optional[Track]:
        """
        Returns the last played track.

        Returns:
            Optional[Track]: Last played track, or None if no history.
        """
        state = self.state
        return state.prev_tracks[-1] if state.prev_tracks else None

    @property
    def last_songs_played(self) -> List[Track]:
        """
        Returns all previously played tracks.

        Returns:
            List[Track]: Previously played tracks.
        """
        return self.state.prev_tracks


@enforce
class EventManager(PlayerStatus):
    """
    Manages events and subscriptions for the Spotify player.

    Args:
        login (Login): The login instance for authentication.
        s_device_id (Optional[str]): Optional device ID to use. If None, a new device ID is generated.
    """

    __slots__ = ("_current_state", "wlock", "_subscriptions", "listener")

    def __init__(self, login: Login, s_device_id: Optional[str] = None) -> None:
        super().__init__(login, s_device_id)
        self._current_state = self.state  # Initialize state for websocket

        self.wlock = threading.Lock()
        self._subscriptions: Dict[str, List[Callable[..., Any]]] = {}

        self.listener = threading.Thread(target=self._listen, daemon=True)
        self.listener.start()

    def _subscribe_callable(self, event: str, func: Callable[..., Any]) -> None:
        """Register a callable for a specific event."""
        with self.wlock:
            if event not in self._subscriptions:
                self._subscriptions[event] = []

            if func not in self._subscriptions[event]:
                self._subscriptions[event].append(func)
            else:
                raise ValueError(
                    f"Function {func.__name__} is already subscribed to event '{event}'"
                )

    def subscribe(self, event: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
        """
        Decorator to subscribe a function to a Spotify websocket event.

        Args:
            event (str): The event name to subscribe to.

        Returns:
            Callable: Decorator that registers the function for the event.
        """

        def decorator(func: Callable[P, R]) -> Callable[P, R]:
            @functools.wraps(func)
            def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
                return func(*args, **kwargs)

            self._subscribe_callable(event, wrapped)
            return wrapped

        return decorator

    def _emit(self, event: str, *args: Any, **kwargs: Any) -> None:
        """
        Emit an event and call all subscribed functions.

        Args:
            event (str): Event name.
            *args: Positional arguments to pass to subscribers.
            **kwargs: Keyword arguments to pass to subscribers.
        """
        if event in self._subscriptions:
            for func in self._subscriptions[event]:
                func(*args, **kwargs)

    def unsubscribe(self, event: str, func: Callable[..., Any]) -> None:
        """
        Unsubscribe a function from an event.

        Args:
            event (str): Event name.
            func (Callable): Function to remove.
        """
        with self.wlock:
            if event in self._subscriptions:
                self._subscriptions[event].remove(func)

    def _listen(self) -> None:
        """Background thread to listen for websocket events and emit them."""
        while True:
            event = self.get_packet()
            if event is None or event.get("payloads") is None:
                continue

            for payload in event["payloads"]:
                self._emit(payload["update_reason"], payload)

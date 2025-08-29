import time
import uuid
from typing import List

from spotapi.login import Login
from spotapi.playlist import PublicPlaylist
from spotapi.song import Song
from spotapi.spotapi_exceptions import PlayerError
from spotapi.spotapi_types.annotations import enforce
from spotapi.status import PlayerStatus
from spotapi.spotapi_utils import random_hex_string

__all__ = ["Player", "PlayerStatus", "PlayerError"]


@enforce
class Player(PlayerStatus):
    """
    Interact with the Spotify player.

    Handles device transfers, playback control, volume management,
    shuffle, repeat, and queue operations.

    Attributes:
        active_id (str): Currently active device ID.
        device_id (str): Origin device ID of the player.
        r_state: Cached player state.
    """

    __slots__ = ("active_id", "device_id", "r_state", "_transferred")

    def __init__(self, login: Login, device_id: str | None = None) -> None:
        """
        Initialize Player and transfer playback to the active device.

        Args:
            login (Login): Authenticated login instance.
            device_id (Optional[str]): Device ID to transfer playback to.
        """
        super().__init__(login, None)

        _devices = self.device_ids
        _active_id = _devices.active_device_id

        if _active_id is None and not device_id:
            raise ValueError(
                "Could not get active device ID. Please provide a device ID."
            )

        self.active_id = device_id or _active_id
        self.r_state = self.state

        if not self.r_state.play_origin:
            raise ValueError("Could not get origin device ID.")

        _origin_device_id = self.r_state.play_origin.device_identifier
        if not _origin_device_id:
            raise ValueError("Could not get origin device ID.")

        self.device_id = _origin_device_id
        self.transfer_player(self.device_id, self.active_id)

    def _build_command_payload(self, endpoint: str, value: dict | None = None) -> dict:
        """
        Helper to build standardized player command payloads.

        Args:
            endpoint (str): The command endpoint.
            value (dict | None): Optional value dictionary for the command.

        Returns:
            dict: Fully constructed payload.
        """
        return {
            "command": {
                **(value or {}),
                "endpoint": endpoint,
                "logging_params": {
                    "command_id": random_hex_string(32),
                    "page_instance_ids": [],
                    "interaction_ids": [],
                },
            }
        }

    def _run_command(
        self, from_device_id: str, to_device_id: str, payload: dict
    ) -> None:
        url = f"https://gue1-spclient.spotify.com/connect-state/v1/player/command/from/{from_device_id}/to/{to_device_id}"
        resp = self.client.post(url, json=payload, authenticate=True)
        if resp.fail:
            raise PlayerError("Could not send command", error=resp.error.string)

    def transfer_player(self, from_device_id: str, to_device_id: str) -> None:
        """Transfer player stream between devices."""
        url = f"https://gue1-spclient.spotify.com/connect-state/v1/connect/transfer/from/{from_device_id}/to/{to_device_id}"
        payload = {
            "transfer_options": {
                "restore_paused": "pause" if self.state.is_paused else "resume"
            },
            "command_id": random_hex_string(32),
        }
        resp = self.client.post(url, json=payload, authenticate=True)
        if resp.fail:
            raise PlayerError("Could not transfer player", error=resp.error.string)
        self._transferred = True

    def run_command(self, command: str) -> None:
        """Sends a generic command to the active player."""
        payload = self._build_command_payload(command)
        self._run_command(self.device_id, self.active_id, payload)

    def _seek_to(self, position_ms: int) -> None:
        self._run_command(
            self.device_id,
            self.active_id,
            self._build_command_payload("seek_to", {"value": position_ms}),
        )

    def _set_shuffle(self, value: bool) -> None:
        self._run_command(
            self.device_id,
            self.active_id,
            self._build_command_payload("set_shuffling_context", {"value": value}),
        )

    def _set_volume(self, volume_percent: float) -> None:
        if not 0 <= volume_percent <= 1.0:
            raise ValueError("Volume must be between 0.0 and 1.0")
        sixteen_bit = int(volume_percent * 65535)
        url = f"https://gue1-spclient.spotify.com/connect-state/v1/connect/volume/from/{self.device_id}/to/{self.active_id}"
        resp = self.client.put(url, json={"volume": sixteen_bit}, authenticate=True)
        if resp.fail:
            raise PlayerError("Could not set volume", error=resp.error.string)

    def _repeat_track(self, value: bool) -> None:
        self._run_command(
            self.device_id,
            self.active_id,
            self._build_command_payload(
                "set_options", {"repeating_context": value, "repeating_track": value}
            ),
        )

    def _add_to_queue(self, track: str) -> None:
        track_id = track.split(":")[-1] if track.startswith("spotify:track:") else track
        self._run_command(
            self.device_id,
            self.active_id,
            self._build_command_payload(
                "add_to_queue",
                {
                    "track": {
                        "uri": f"spotify:track:{track_id}",
                        "metadata": {"is_queued": "true"},
                        "provider": "queue",
                    }
                },
            ),
        )

    def _play_song(self, track: str, playlist: str, track_uid: str) -> None:
        track_id = track.split(":")[-1] if track.startswith("spotify:track:") else track
        playlist_id = (
            playlist.split(":")[-1]
            if playlist.startswith("spotify:playlist:")
            else playlist
        )
        payload = {
            "command": {
                "context": {
                    "uri": f"spotify:playlist:{playlist_id}",
                    "url": f"context://spotify:playlist:{playlist_id}",
                    "metadata": {},
                },
                "play_origin": {
                    "feature_identifier": "playlist",
                    "feature_version": "web-player_2024-08-20_1724112418648_eba321c",
                    "referrer_identifier": "home",
                },
                "options": {
                    "license": "tft",
                    "skip_to": {
                        "track_uid": track_uid,
                        "track_index": 1,
                        "track_uri": f"spotify:track:{track_uid}",
                    },
                    "player_options_override": {},
                },
                "logging_params": {
                    "page_instance_ids": [str(uuid.uuid4())],
                    "interaction_ids": [str(uuid.uuid4())],
                    "command_id": random_hex_string(32),
                },
                "endpoint": "play",
            }
        }
        self._run_command(self.device_id, self.active_id, payload)

    def set_shuffle(self, value: bool) -> None:
        """Enable or disable shuffle."""
        self._set_shuffle(value)

    def seek_to(self, position_ms: int) -> None:
        """Seek to a specific position."""
        self._seek_to(position_ms)

    def restart_song(self) -> None:
        """Restart the current song."""
        self.seek_to(0)

    def pause(self) -> None:
        """Pause the player."""
        self.run_command("pause")

    def resume(self) -> None:
        """Resume playback."""
        self.run_command("resume")

    def skip_next(self) -> None:
        """Skip to next track."""
        self.run_command("skip_next")

    def skip_prev(self) -> None:
        """Skip to previous track."""
        self.run_command("skip_prev")

    def add_to_queue(self, track: str) -> None:
        """Add track to queue."""
        self._add_to_queue(track)

    def play_track(self, track: str, playlist: str) -> None:
        """Play a specific track from a playlist."""
        track_id = track.split(":")[-1] if track.startswith("spotify:track:") else track
        uids: List[str] = []

        playlist_gen = PublicPlaylist(playlist).paginate_playlist()
        for chunk in playlist_gen:
            items = chunk["items"]
            parsed_uids, stop = Song.parse_playlist_items(
                items, song_id=track_id, all_instances=True
            )
            uids.extend(parsed_uids)
            if stop:
                playlist_gen.close()
                break

        self._play_song(track, playlist, uids[0])

    def repeat_track(self, value: bool) -> None:
        """Repeat or stop repeating the current track."""
        self._repeat_track(value)

    def set_volume(self, volume_percent: float) -> None:
        """Set player volume (0.0 - 1.0)."""
        self._set_volume(volume_percent)

    def fade_in_volume(
        self,
        volume_percent: float,
        duration_ms: int = 500,
        request_time_ms: int | None = None,
    ) -> None:
        """
        Gradually adjust volume over a duration.

        Args:
            volume_percent (float): Target volume (0.0 - 1.0).
            duration_ms (int): Total duration of fade in ms.
            request_time_ms (Optional[int]): Time already spent on request.
        """
        if not 0.0 <= volume_percent <= 1.0:
            raise ValueError("Volume must be between 0.0 and 1.0")

        duration_ms = duration_ms - (request_time_ms or 0)
        if duration_ms <= 0:
            raise ValueError("Effective duration must be positive")

        target_volume = volume_percent * 65535
        current_volume = self.device_ids.devices[self.active_id].volume

        if current_volume == target_volume:
            return

        steps = 100
        step_duration = duration_ms / steps
        step_increment = (target_volume - current_volume) / steps

        for _ in range(steps):
            current_volume = max(0, min(current_volume + step_increment, 65535))
            self._set_volume(current_volume / 65535)
            time.sleep(step_duration / 1000)

        self._set_volume(volume_percent)

from __future__ import annotations

import atexit
import json
import signal
import threading
import time
from typing import Any, Dict

from websockets.sync.client import connect

from spotapi.client import BaseClient
from spotapi.exceptions import WebSocketError
from spotapi.login import Login
from spotapi.spotapitypes.annotations import enforce
from spotapi.utils.strings import random_hex_string

__all__ = ["WebsocketStreamer", "WebSocketError"]


@enforce
class WebsocketStreamer:
    """
    Standard streamer to connect to Spotify's WebSocket API.

    Args:
        login (Login): Authenticated login object.
    """

    __slots__ = (
        "base",
        "client",
        "device_id",
        "ws",
        "rlock",
        "ws_dump",
        "connection_id",
        "keep_alive_thread",
    )

    def __init__(self, login: Login) -> None:
        """Initializes the WebSocket connection and registers the device.

        Args:
            login (Login): Authenticated login object.

        Raises:
            ValueError: If login is not authenticated.
        """
        if not login.logged_in:
            raise ValueError("Must be logged in")

        self.base: BaseClient = BaseClient(login.client)
        self.client = self.base.client

        self.base.get_session()
        self.base.get_client_token()

        self.device_id: str = random_hex_string(32)

        uri = f"wss://dealer.spotify.com/?access_token={self.base.access_token}"
        self.ws = connect(
            uri,
            user_agent_header=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )

        self.rlock: threading.Lock = threading.Lock()
        self.ws_dump: Dict[Any, Any] | None = None
        self.connection_id: str = self.get_init_packet()

        self.keep_alive_thread = threading.Thread(target=self.keep_alive, daemon=True)
        self.keep_alive_thread.start()

        atexit.register(self.ws.close)
        signal.signal(signal.SIGINT, self.handle_interrupt)

    def register_device(self) -> None:
        """Registers the current device with Spotify for playback control.

        Raises:
            WebSocketError: If device registration fails.
        """
        url = "https://gue1-spclient.spotify.com/track-playback/v1/devices"
        payload: Dict[str, Any] = {
            "device": {
                "brand": "spotify",
                "capabilities": {
                    "change_volume": True,
                    "enable_play_token": True,
                    "supports_file_media_type": True,
                    "play_token_lost_behavior": "pause",
                    "disable_connect": False,
                    "audio_podcasts": True,
                    "video_playback": True,
                    "manifest_formats": [
                        "file_ids_mp3",
                        "file_urls_mp3",
                        "manifest_urls_audio_ad",
                        "manifest_ids_video",
                        "file_urls_external",
                        "file_ids_mp4",
                        "file_ids_mp4_dual",
                        "manifest_urls_audio_ad",
                    ],
                },
                "device_id": self.device_id,
                "device_type": "computer",
                "metadata": {},
                "model": "web_player",
                "name": "Web Player (Chrome)",
                "platform_identifier": "web_player windows 10;chrome 120.0.0.0;desktop",
                "is_group": False,
            },
            "outro_endcontent_snooping": False,
            "connection_id": self.connection_id,
            "client_version": "harmony:4.43.2-a61ecaf5",
            "volume": 65535,
        }

        resp = self.client.post(url, json=payload, authenticate=True)
        if resp.fail:
            raise WebSocketError("Could not register device", error=resp.error.string)

    def connect_device(self) -> Dict[str, Any]:
        """Connects the device to Spotify and returns its state.

        Returns:
            Dict[str, Any]: Current device state.

        Raises:
            WebSocketError: If connecting the device fails.
        """
        url = f"https://gue1-spclient.spotify.com/connect-state/v1/devices/hobs_{self.device_id}"
        payload: Dict[str, Any] = {
            "member_type": "CONNECT_STATE",
            "device": {
                "device_info": {
                    "capabilities": {
                        "can_be_player": False,
                        "hidden": True,
                        "needs_full_player_state": True,
                    }
                }
            },
        }
        headers: Dict[str, str] = {"x-spotify-connection-id": self.connection_id}

        resp = self.client.put(url, json=payload, authenticate=True, headers=headers)
        if resp.fail:
            raise WebSocketError("Could not connect device", error=resp.error.string)

        return resp.response

    def keep_alive(self) -> None:
        """Sends a ping to the WebSocket every 60 seconds to keep the connection alive."""
        while True:
            try:
                time.sleep(60)
                with self.rlock:
                    self.ws.send('{"type":"ping"}')
            except (ConnectionError, KeyboardInterrupt):
                break

    def get_packet(self) -> Dict[Any, Any]:
        """Receives the next packet from the WebSocket.

        Returns:
            Dict[Any, Any]: The latest WebSocket message.
        """
        with self.rlock:
            ws_dump = dict(json.loads(self.ws.recv()))
            self.ws_dump = ws_dump
            return self.ws_dump

    def get_init_packet(self) -> str:
        """Gets the Spotify connection ID from the initial WebSocket packet.

        Returns:
            str: Spotify connection ID.

        Raises:
            ValueError: If the init packet is invalid or missing the connection ID.
        """
        packet = self.get_packet()
        headers = packet.get("headers") or {}
        connection_id = headers.get("Spotify-Connection-Id")

        if connection_id is None:
            raise ValueError("Invalid init packet")

        return connection_id

    def handle_interrupt(self, signum: int, frame: Any) -> None:
        """Handles SIGINT (Ctrl+C) and gracefully closes the WebSocket connection.

        Args:
            signum (int): Signal number.
            frame (Any): Current stack frame.
        """
        self.ws.close()
        exit(0)

import os
import time
from datetime import datetime
from threading import Lock
from typing import Any

from colorama import Fore, Style, init

from spotapi.spotapi_types import LoggerProtocol

__all__ = ["Logger", "NoopLogger", "LoggerProtocol"]

# Enable colorama for Windows
if os.name == "nt":
    os.system("")

init(autoreset=True)

LOCK = Lock()


class Logger(LoggerProtocol):
    """A simple thread-safe stdout logger with color formatting."""

    LEVEL_COLORS = {
        "fatal": Fore.LIGHTBLACK_EX,
        "error": Fore.LIGHTRED_EX,
        "warn": Fore.LIGHTYELLOW_EX,
        "attempt": Fore.LIGHTMAGENTA_EX,
        "info": Fore.LIGHTGREEN_EX,
    }

    @staticmethod
    def __fmt_time() -> str:
        t = datetime.now().strftime("%H:%M:%S")
        return f"[{Style.BRIGHT}{Fore.LIGHTCYAN_EX}{t}{Style.RESET_ALL}]"

    @staticmethod
    def _log(level: str, s: str, **extra: Any) -> None:
        with LOCK:
            color = Logger.LEVEL_COLORS.get(level, Fore.WHITE)
            fields = [
                f"{Style.BRIGHT}{Fore.LIGHTBLUE_EX}{k}={color}{v}{Style.RESET_ALL}"
                for k, v in extra.items()
            ]
            print(
                f"{Logger.__fmt_time()} {color}{s}{Style.RESET_ALL} " + " ".join(fields)
            )

    @staticmethod
    def fatal(s: str, **extra: Any) -> None:
        Logger._log("fatal", s, **extra)
        time.sleep(5)
        os._exit(1)

    @staticmethod
    def error(s: str, **extra: Any) -> None:
        Logger._log("error", s, **extra)

    @staticmethod
    def warn(s: str, **extra: Any) -> None:
        Logger._log("warn", s, **extra)

    @staticmethod
    def attempt(s: str, **extra: Any) -> None:
        Logger._log("attempt", s, **extra)

    @staticmethod
    def info(s: str, **extra: Any) -> None:
        Logger._log("info", s, **extra)


class NoopLogger(LoggerProtocol):
    @staticmethod
    def error(s: str, **extra: Any) -> None: ...
    @staticmethod
    def info(s: str, **extra: Any) -> None: ...
    @staticmethod
    def fatal(s: str, **extra: Any) -> None: ...
    @staticmethod
    def attempt(s: str, **extra: Any) -> None: ...

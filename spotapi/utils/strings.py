"""
Utility functions for generating random strings, emails, domains, and parsing JSON-like strings.
"""

import base64
import os
import random
import string
from typing import Optional

__all__ = [
    "random_b64_string",
    "random_hex_string",
    "parse_json_string",
    "random_string",
    "random_domain",
    "random_email",
    "random_dob",
    "random_nonce",
]


def random_b64_string(length: int) -> str:
    """Generate a random base64-encoded string of given length.

    Args:
        length (int): Length of the raw random string before encoding.

    Returns:
        str: Base64 encoded random string.

    Note:
        This is used by Spotify internally.
    """
    random_string = "".join(chr(random.randint(0, 255)) for _ in range(length))
    encoded_string = base64.b64encode(random_string.encode("latin1")).decode("ascii")
    return encoded_string


def random_hex_string(length: int) -> str:
    """Generate a random hexadecimal string of given length.

    Args:
        length (int): Desired hex string length.

    Returns:
        str: Random hexadecimal string.

    Note:
        This is used by Spotify internally.
    """
    num_bytes = (length + 1) // 2
    random_bytes = os.urandom(num_bytes)
    return random_bytes.hex()[:length]


def parse_json_string(b: str, s: str) -> str:
    """Extract a value from a simple JSON-like string.

    Args:
        b (str): Input JSON-like string.
        s (str): Key name to search for.

    Returns:
        str: Extracted value.

    Raises:
        ValueError: If key or closing quote is not found.
    """
    start_index = b.find(f'{s}":"')
    if start_index == -1:
        raise ValueError(f'Substring "{s}":" not found in JSON string')

    value_start_index = start_index + len(s) + 3
    value_end_index = b.find('"', value_start_index)
    if value_end_index == -1:
        raise ValueError(f'Closing double quote not found after "{s}":"')

    return b[value_start_index:value_end_index]


def random_string(length: int, /, strong: Optional[bool] = False) -> str:
    """Generate a random alphabetic string with optional strong characters.

    Args:
        length (int): Length of the string.
        strong (bool, optional): If True, adds digits and special characters. Defaults to False.

    Returns:
        str: Randomly generated string.
    """
    letters = string.ascii_letters
    rnd = "".join(random.choice(letters) for _ in range(length))

    if strong:
        rnd += random.choice(string.digits)
        rnd += random.choice("@$%&*!?")

    return rnd


def random_domain() -> str:
    """Return a random email domain from a predefined list.

    Returns:
        str: Random email domain.
    """
    domains = [
        "gmail.com",
        "outlook.com",
        "yahoo.com",
        "hotmail.com",
        "aol.com",
        "comcast.net",
        "icloud.com",
        "msn.com",
        "live.com",
        "protonmail.com",
        "yandex.com",
        "tutanota.com",
    ]
    return random.choice(domains)


def random_email() -> str:
    """Generate a random email address.

    Returns:
        str: Random email in the form `{random}@{domain}`.
    """
    return f"{random_string(10)}@{random_domain()}"


def random_dob() -> str:
    """Generate a random date of birth string.

    Returns:
        str: Date of birth in `YYYY-MM-DD` format.
    """
    return f"{random.randint(1950, 2000)}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"


def random_nonce() -> str:
    """Generate a random nonce string.

    Returns:
        str: Concatenation of two random 32-bit integers as string.
    """
    return "".join(str(random.getrandbits(32)) for _ in range(2))

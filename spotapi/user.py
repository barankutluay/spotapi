from __future__ import annotations

from collections.abc import Mapping as MappingABC
from typing import Any, Mapping

from spotapi import utils
from spotapi.exceptions import UserError
from spotapi.login import Login
from spotapi.spotapitypes.annotations import enforce

__all__ = ["User", "UserError"]


@enforce
class User:
    """
    Represents a Spotify user account.

    Args:
        login (Login): The login object used for authentication.
    """

    __slots__ = ("login", "_user_plan", "_user_info", "csrf_token")

    def __init__(self, login: Login) -> None:
        """Initializes the User instance.

        Raises:
            ValueError: If the login object is not authenticated.
        """
        if not login.logged_in:
            raise ValueError("Must be logged in")

        self.login: Login = login
        self._user_plan: Mapping[str, Any] | None = None
        self._user_info: Mapping[str, Any] | None = None
        self.csrf_token: str | None = None

    @property
    def has_premium(self) -> bool:
        """Indicates whether the user has a premium plan.

        Returns:
            bool: True if the user has a premium plan, False otherwise.
        """
        if self._user_plan is None:
            self._user_plan = self.get_plan_info()

        return self._user_plan["plan"]["name"] != "Spotify Free"

    @property
    def username(self) -> str:
        """Gets the Spotify username of the account.

        Returns:
            str: The user's Spotify username.
        """
        if self._user_info is None:
            self._user_info = self.get_user_info()

        return self._user_info["profile"]["username"]

    def get_plan_info(self) -> Mapping[str, Any]:
        """Fetches the user's subscription plan information.

        Returns:
            Mapping[str, Any]: The user's plan details.

        Raises:
            UserError: If the request fails or returns invalid JSON.
        """
        url = "https://www.spotify.com/ca-en/api/account/v2/plan/"
        resp = self.login.client.get(url)

        if resp.fail:
            raise UserError("Could not get user plan info", error=resp.error.string)

        if not isinstance(resp.response, MappingABC):
            raise UserError("Invalid JSON")

        return resp.response

    def verify_login(self) -> bool:
        """Verifies if the current login session is valid.

        Returns:
            bool: True if login is valid, False if session is expired (401).

        Raises:
            Exception: Re-raises any exceptions that are not 401 unauthorized.
        """
        try:
            self.get_plan_info()
        except Exception as e:
            if "401" in str(e):
                return False
            raise e
        else:
            return True

    def get_user_info(self) -> Mapping[str, Any]:
        """Fetches the user's account profile information.

        Returns:
            Mapping[str, Any]: User profile details.

        Raises:
            UserError: If the request fails or returns invalid JSON.
        """
        url = "https://www.spotify.com/api/account-settings/v1/profile"
        resp = self.login.client.get(url)

        if resp.fail:
            raise UserError("Could not get user info", error=resp.error.string)

        if not isinstance(resp.response, MappingABC):
            raise UserError("Invalid JSON")

        self.csrf_token = resp.raw.headers.get("X-Csrf-Token")
        return resp.response

    def edit_user_info(self, dump: Mapping[str, Any]) -> None:
        """Edits the user's profile information.

        For this method to work, `dump` must be the full profile dump from `get_user_info()`.
        Only modify the fields you wish to update.

        Args:
            dump (Mapping[str, Any]): Full user profile dump with modifications.

        Raises:
            UserError: If the captcha solver is not set or the request fails.
        """
        if self.login.solver is None:
            raise UserError("Captcha solver not set")

        captcha_response = self.login.solver.solve_captcha(
            "https://www.spotify.com",
            "6LfCVLAUAAAAALFwwRnnCJ12DalriUGbj8FW_J39",
            "account_settings/profile_update",
            "v3",
        )

        if not captcha_response:
            raise UserError("Could not solve captcha")

        profile_dump = dump["profile"]
        payload: dict[str, Any] = {
            "profile": {
                "email": profile_dump["email"],
                "gender": profile_dump["gender"],
                "birthdate": profile_dump["birthdate"],
                "country": profile_dump["country"],
            },
            "recaptcha_token": captcha_response,
            "client_nonce": utils.random_nonce(),
            "callback_url": "https://www.spotify.com/account/profile/challenge",
            "client_info": {"locale": "en_US", "capabilities": [1]},
        }

        url = "https://www.spotify.com/api/account-settings/v2/profile"
        headers = {"Content-Type": "application/json", "X-Csrf-Token": self.csrf_token}

        resp = self.login.client.put(url, json=payload, headers=headers)

        if resp.fail:
            raise UserError("Could not edit user info", error=resp.error.string)

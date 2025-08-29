from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any, Optional
from urllib.parse import quote, urlencode

from spotapi.spotapi_exceptions import LoginError
from spotapi.spotapi_types import Config, SaverProtocol
from spotapi.spotapi_types.annotations import enforce
from spotapi.spotapi_utils.strings import parse_json_string

__all__ = ["Login", "LoginChallenge", "LoginError"]


@enforce
class Login:
    """
    Handles Spotify user login.

    This class manages login flow including session retrieval, captcha solving,
    password submission, and optional challenge handling.

    Attributes:
        solver: Configured captcha solver.
        client: HTTP client from configuration.
        logger: Logger instance from configuration.
        password (str): User's password.
        identifier_credentials (str): Email or username.
        _authorized (bool): Internal flag for login status.
        csrf_token (Optional[str]): CSRF token for login requests.
        flow_id (Optional[str]): Flow ID for login session.

    Raises:
        ValueError: If neither email nor username is provided.
        LoginError: If any network request or login step fails.
    """

    __slots__ = (
        "solver",
        "client",
        "logger",
        "password",
        "identifier_credentials",
        "_authorized",
        "csrf_token",
        "flow_id",
    )

    # Endpoints
    LOGIN_URL = "https://accounts.spotify.com/en/login"
    PASSWORD_URL = "https://accounts.spotify.com/login/password"
    SYNC_URLS = [
        "https://open.spotify.com/",
        "https://pixel.spotify.com/v2/sync?ce=1&pp=",
    ]

    SITE_KEY_V3 = "6LfCVLAUAAAAALFwwRnnCJ12DalriUGbj8FW_J39"

    def __init__(
        self,
        cfg: Config,
        password: str,
        *,
        email: Optional[str] = None,
        username: Optional[str] = None,
    ) -> None:
        """
        Initialize a Spotify login session handler.

        Args:
            cfg (Config): Configuration containing solver, client, and logger.
            password (str): User's password.
            email (Optional[str]): User email (optional if username provided).
            username (Optional[str]): Username (optional if email provided).

        Raises:
            ValueError: If neither email nor username is provided.
        """
        self.solver = cfg.solver
        self.client = cfg.client
        self.logger = cfg.logger

        self.password = password
        self.identifier_credentials: Optional[str] = username or email

        if self.identifier_credentials is None:
            raise ValueError("Must provide an email or username")

        self.client.fail_exception = LoginError
        self._authorized: bool = False
        self.csrf_token: Optional[str] = None
        self.flow_id: Optional[str] = None

    def save(self, saver: SaverProtocol) -> None:
        """
        Save the current login session.

        Args:
            saver (SaverProtocol): Saver to persist session data.

        Raises:
            ValueError: If the session is not logged in.
        """
        if not self.logged_in:
            raise ValueError("Cannot save session if it is not logged in")

        saver.save(
            [
                {
                    "identifier": self.identifier_credentials,
                    "password": self.password,
                    "cookies": self.client.cookies.get_dict(),
                }
            ]
        )

    @classmethod
    def from_cookies(cls, dump: Mapping[str, Any], cfg: Config) -> Login:
        """
        Create a Login instance from cookie data.

        Args:
            dump (Mapping[str, Any]): Session dump including identifier and cookies.
            cfg (Config): Configuration object.

        Returns:
            Login: Login instance with cookies set.

        Raises:
            ValueError: If dump is missing required fields.
        """
        password = dump.get("password") or ""
        cred = dump.get("identifier")
        cookies = dump.get("cookies")

        if isinstance(cookies, str):
            parsed: dict[str, str] = {}
            for cookie in cookies.replace(" ", "").split(";"):
                if "=" in cookie:
                    k, v = cookie.split("=", 1)
                    parsed[k] = v
            cookies = parsed

        if not (cred and isinstance(cookies, Mapping)):
            raise ValueError(
                "Invalid dump format: must contain 'identifier' and 'cookies'"
            )

        cfg.client.cookies.clear()
        for k, v in cookies.items():
            cfg.client.cookies.set(k, v, domain=".spotify.com", path="/")

        instance = cls(cfg, password, email=cred, username=cred)
        instance.logged_in = True
        return instance

    @classmethod
    def from_saver(
        cls, saver: SaverProtocol, cfg: Config, identifier: str, **kwargs
    ) -> Login:
        """
        Load a Login session from a Saver.

        Args:
            saver (SaverProtocol): Saver to load session data from.
            cfg (Config): Configuration object.
            identifier (str): Session identifier.

        Returns:
            Login: Restored login instance.
        """
        dump = saver.load(query={"identifier": identifier}, **kwargs)
        return cls.from_cookies(dump, cfg)

    @property
    def logged_in(self) -> bool:
        """Indicates whether the user is logged in."""
        return self._authorized

    @logged_in.setter
    def logged_in(self, value: bool) -> None:
        self._authorized = value

    def __repr__(self) -> str:
        return (
            f"Login(password={self.password!r}, "
            f"identifier_credentials={self.identifier_credentials!r})"
        )

    def __str__(self) -> str:
        return (
            f"Logged in with ID={self.identifier_credentials}, password={self.password}"
        )

    def _get_add_cookie(self, url: Optional[str] = None) -> None:
        """
        Perform GET requests to ensure cookies are updated.

        Args:
            url (Optional[str]): Optional URL. If not provided, sync URLs are used.

        Raises:
            LoginError: If cookie fetch fails.
        """
        urls = [url] if url else self.SYNC_URLS
        for u in urls:
            resp = self.client.get(u)
            if resp.fail:
                raise LoginError("Could not get session", error=resp.error.string)

    def _set_non_otc(self) -> None:
        """
        Retrieve non-OTC session and CSRF token.

        Raises:
            LoginError: If non-OTC session cannot be retrieved.
        """
        params = {
            "login_hint": self.identifier_credentials,
            "allow_password": 1,
            "continue": f"https://open.spotify.com/?flow_ctx={self.flow_id}",
            "flow_ctx": self.flow_id,
        }
        resp = self.client.get(self.LOGIN_URL, params=params)
        if resp.fail:
            raise LoginError("Could not get non-OTC session", error=resp.error.string)

        self.csrf_token = resp.raw.cookies.get("sp_sso_csrf_token")

    def _get_session(self) -> None:
        """
        Initialize login session by retrieving CSRF token and flow ID.

        Raises:
            LoginError: If session cannot be retrieved.
        """
        resp = self.client.get(self.LOGIN_URL)
        if resp.fail:
            raise LoginError("Could not get session", error=resp.error.string)

        self.csrf_token = resp.raw.cookies.get("sp_sso_csrf_token")
        self.flow_id = parse_json_string(resp.response, "flowCtx")

        self.client.cookies.set(
            "remember", quote(self.identifier_credentials or "")
        )  # type: ignore
        self._get_add_cookie()
        self._set_non_otc()

    def _password_payload(self, captcha_key: str) -> str:
        """
        Construct URL-encoded payload for password submission.

        Args:
            captcha_key (str): Solved captcha token.

        Returns:
            str: URL-encoded payload string.
        """
        query = {
            "username": self.identifier_credentials,
            "password": self.password,
            "recaptchaToken": captcha_key,
            "continue": f"https://open.spotify.com/?flow_ctx={self.flow_id}",
            "flowCtx": self.flow_id,
        }
        return urlencode(query)

    def _submit_password(self, token: str) -> None:
        """
        Submit login password with captcha token.

        Args:
            token (str): Captcha token.

        Raises:
            LoginError: If request fails or login unsuccessful.
        """
        payload = self._password_payload(token)
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Csrf-Token": self.csrf_token,
        }
        resp = self.client.post(self.PASSWORD_URL, data=payload, headers=headers)
        if resp.fail:
            raise LoginError("Could not submit password", error=resp.error.string)

        self.csrf_token = resp.raw.cookies.get("sp_sso_csrf_token")
        self.handle_login_error(resp.response)
        self.logged_in = True
        self._get_add_cookie(f"https://open.spotify.com/?flow_ctx={self.flow_id}")

    def handle_login_error(self, json_data: Mapping[str, Any]) -> None:
        """
        Process login response and handle errors.

        Args:
            json_data (Mapping[str, Any]): Response JSON.

        Raises:
            LoginError: For invalid or unexpected responses.
        """
        result = json_data.get("result")
        if result == "ok":
            return

        if result == "redirect_required":
            self.logger.attempt("Challenge detected, attempting to solve")
            LoginChallenge(self, json_data).defeat()
            self.logger.info("Challenge solved")
            return

        if "error" not in json_data:
            raise LoginError(f"Unexpected response format: {json_data}")

        error_type = json_data["error"]
        match error_type:
            case "errorUnknown":
                raise LoginError("ErrorUnknown, Needs retrying")
            case "errorInvalidCredentials":
                raise LoginError(
                    "Invalid Credentials", error=f"{str(self)}: {error_type}"
                )
            case _:
                raise LoginError("Unforeseen Error", error=f"{str(self)}: {error_type}")

    def login(self) -> None:
        """
        Execute the full login flow:
            1. Retrieve session and CSRF token.
            2. Solve captcha.
            3. Submit password.
            4. Handle challenges if required.

        Raises:
            LoginError: If any step fails.
        """
        if self.logged_in:
            raise LoginError("User already logged in")

        start = time.time()
        self._get_session()
        self.logger.attempt("Solving captcha...")

        if self.solver is None:
            raise LoginError("Solver not set")

        captcha_response = self.solver.solve_captcha(
            self.LOGIN_URL,
            self.SITE_KEY_V3,
            "accounts/login",
            "v3",
        )
        if not captcha_response:
            raise LoginError("Could not solve captcha")

        self.logger.info("Solved captcha", time_taken=f"{int(time.time() - start)}s")
        self._submit_password(captcha_response)
        self.logger.info(
            "Logged in successfully", time_taken=f"{int(time.time() - start)}s"
        )


class LoginChallenge:
    """
    Handles Spotify login challenge flow (RecaptchaV2).

    Attributes:
        l (Login): Login instance.
        dump (Mapping[str, Any]): Challenge response dump.
        challenge_url (str): URL of the challenge.
        interaction_hash (Optional[str]): Challenge interaction hash.
        interaction_reference (Optional[str]): Challenge interaction reference.
        challenge_session_id (Optional[str]): Challenge session ID.
        session_id (Optional[str]): Session ID extracted from URL.

    Raises:
        LoginError: If challenge retrieval or submission fails.
    """

    __slots__ = (
        "l",
        "dump",
        "challenge_url",
        "interaction_hash",
        "interaction_reference",
        "challenge_session_id",
        "session_id",
    )

    SITE_KEY_V2 = "6LeO36obAAAAALSBZrY6RYM1hcAY7RLvpDDcJLy3"

    def __init__(self, login: Login, dump: Mapping[str, Any]) -> None:
        """
        Initialize a Spotify login challenge handler.

        Args:
            login (Login): Login instance that triggered the challenge.
            dump (Mapping[str, Any]): Challenge response dump from Spotify,
                must contain 'data.redirect_url'.

        Raises:
            KeyError: If required keys are missing in the dump.
        """
        self.l = login
        self.dump = dump
        self.challenge_url: str = self.dump["data"]["redirect_url"]
        self.interaction_hash: Optional[str] = None
        self.interaction_reference: Optional[str] = None
        self.challenge_session_id: Optional[str] = None
        self.session_id: Optional[str] = None

    def _get_challenge(self) -> None:
        """
        Retrieve the challenge page.

        Raises:
            LoginError: If challenge page cannot be retrieved.
        """
        resp = self.l.client.get(self.challenge_url)
        if resp.fail:
            raise LoginError("Could not get challenge", error=resp.error.string)

    def _construct_challenge_payload(self) -> Mapping[str, Any]:
        """
        Build payload for challenge submission.

        Returns:
            Mapping[str, Any]: Payload containing challenge data.

        Raises:
            LoginError: If solver not set or captcha cannot be solved.
        """
        if self.l.solver is None:
            raise LoginError("Solver not set")

        captcha_response = self.l.solver.solve_captcha(
            "https://challenge.spotify.com",
            self.SITE_KEY_V2,
            "accounts/login",
            "v2",
        )
        if not captcha_response:
            raise LoginError("Could not solve captcha")

        self.session_id = self.challenge_url.split("c/")[1].split("/")[0]
        challenge_id = self.challenge_url.split(self.session_id + "/")[1].split("/")[0]

        return {
            "url": "https://challenge.spotify.com/api/v1/invoke-challenge-command",
            "json": {
                "session_id": self.session_id,
                "challenge_id": challenge_id,
                "recaptcha_challenge_v1": {
                    "solve": {"recaptcha_token": captcha_response}
                },
            },
            "headers": {"Content-Type": "application/json"},
        }

    def _submit_challenge(self) -> None:
        """
        Submit captcha response to challenge endpoint.

        Raises:
            LoginError: If submission fails or response invalid.
        """
        payload = self._construct_challenge_payload()
        resp = self.l.client.post(**payload)
        if resp.fail:
            raise LoginError("Could not submit challenge", error=resp.error.string)

        if not isinstance(resp.response, Mapping):
            raise LoginError("Invalid JSON in challenge response")

        self.interaction_hash = resp.response["completed"]["hash"]
        self.interaction_reference = resp.response["completed"]["interaction_reference"]

    def _complete_challenge(self) -> None:
        """
        Complete challenge by following redirect.

        Raises:
            LoginError: If challenge completion fails.
        """
        url = (
            f"https://accounts.spotify.com/login/challenge-completed"
            f"?sessionId={self.session_id}&interact_ref={self.interaction_reference}"
            f"&hash={self.interaction_hash}"
        )
        resp = self.l.client.get(url)
        if resp.fail:
            raise LoginError("Could not complete challenge", error=resp.error.string)

    def defeat(self) -> None:
        """
        Execute full RecaptchaV2 challenge flow.

        Steps:
            1. Retrieve challenge page.
            2. Submit solved captcha.
            3. Complete challenge by visiting completion URL.

        Raises:
            LoginError: If any step fails.
        """
        self._get_challenge()
        self._submit_challenge()
        self._complete_challenge()

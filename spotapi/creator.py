import json
import time
import uuid
from typing import Any, Dict, Optional

from spotapi.exceptions import GeneratorError
from spotapi.http.request import TLSClient
from spotapi.spotapitypes import Config
from spotapi.spotapitypes.annotations import enforce
from spotapi.utils.strings import (
    parse_json_string,
    random_dob,
    random_email,
    random_string,
)

__all__ = ["Creator", "AccountChallenge", "GeneratorError"]


@enforce
class Creator:
    """
    Handles Spotify account creation, including session retrieval,
    captcha solving, payload submission, and embedded challenge handling.

    Attributes:
        cfg (Config): Configuration object containing solver, client, and logger.
        email (str): Email address for the account.
        password (str): Password for the account.
        display_name (str): Display name for the account.
        birthdate (str): Birthdate in YYYY-MM-DD format.
        gender (int): Gender value.
        client (TLSClient): HTTP client from configuration.
        submission_id (str): Unique UUID for registration attempt.
        api_key (Optional[str]): API key obtained from Spotify session.
        installation_id (Optional[str]): Installation ID from session.
        csrf_token (Optional[str]): CSRF token from session.
        flow_id (Optional[str]): Flow ID for the registration process.
    """

    __slots__ = (
        "cfg",
        "email",
        "password",
        "display_name",
        "birthdate",
        "gender",
        "client",
        "submission_id",
        "api_key",
        "installation_id",
        "csrf_token",
        "flow_id",
    )

    SIGNUP_URL = "https://www.spotify.com/ca-en/signup"
    CREATE_ACCOUNT_URL = (
        "https://spclient.wg.spotify.com/signup/public/v2/account/create"
    )
    SITE_KEY = "6LfCVLAUAAAAALFwwRnnCJ12DalriUGbj8FW_J39"

    def __init__(
        self,
        cfg: Config,
        email: Optional[str] = None,
        password: Optional[str] = None,
        display_name: Optional[str] = None,
        birthdate: Optional[str] = None,
        gender: int = 1,
    ) -> None:
        """
        Initialize a Creator object for Spotify account creation.

        Args:
            cfg (Config): Configuration object containing client, solver, and logger.
            email (Optional[str]): Email for the new account. Defaults to a random email if None.
            password (Optional[str]): Password for the new account. Defaults to a strong random password if None.
            display_name (Optional[str]): Display name for the account. Defaults to a random string if None.
            birthdate (Optional[str]): Birthdate in YYYY-MM-DD format. Defaults to a random date if None.
            gender (int): Gender value (1=male, 2=female, etc.). Defaults to 1.
        """
        self.cfg = cfg
        self.email = email or random_email()
        self.password = password or random_string(10, strong=True)
        self.display_name = display_name or random_string(10)
        self.birthdate = birthdate or random_dob()
        self.gender = gender

        self.client: TLSClient = self.cfg.client
        self.submission_id: str = str(uuid.uuid4())
        self.api_key: Optional[str] = None
        self.installation_id: Optional[str] = None
        self.csrf_token: Optional[str] = None
        self.flow_id: Optional[str] = None

    def _get_session(self) -> None:
        """Retrieve Spotify signup session and extract tokens.

        Raises:
            GeneratorError: If session retrieval fails.
        """
        resp = self.client.get(self.SIGNUP_URL)
        if resp.fail:
            raise GeneratorError("Could not get session", error=resp.error.string)

        self.api_key = parse_json_string(resp.response, "signupServiceAppKey")
        self.installation_id = parse_json_string(resp.response, "spT")
        self.csrf_token = parse_json_string(resp.response, "csrfToken")
        self.flow_id = parse_json_string(resp.response, "flowId")

    def _post_request(
        self,
        url: str,
        payload: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Send a POST request using TLSClient and return JSON response.

        Args:
            url (str): Endpoint URL.
            payload (Dict[str, Any]): JSON payload.
            headers (Optional[Dict[str, str]]): Optional HTTP headers.

        Returns:
            Dict[str, Any]: Parsed JSON response.

        Raises:
            GeneratorError: If request fails.
        """
        resp = self.client.post(url, json=payload, headers=headers or {})
        if resp.fail:
            raise GeneratorError(f"Request to {url} failed", error=resp.error.string)
        return resp.response

    def _build_payload(self, captcha_token: str) -> Dict[str, Any]:
        """Construct the registration payload.

        Args:
            captcha_token (str): Solved captcha token.

        Returns:
            Dict[str, Any]: Payload ready for submission.
        """
        return {
            "account_details": {
                "birthdate": self.birthdate,
                "consent_flags": {
                    "eula_agreed": True,
                    "send_email": True,
                    "third_party_email": False,
                },
                "display_name": self.display_name,
                "email_and_password_identifier": {
                    "email": self.email,
                    "password": self.password,
                },
                "gender": self.gender,
            },
            "callback_uri": f"https://www.spotify.com/signup/challenge?flow_ctx={self.flow_id}%{int(time.time())}&locale=ca-en",
            "client_info": {
                "api_key": self.api_key,
                "app_version": "v2",
                "capabilities": [1],
                "installation_id": self.installation_id,
                "platform": "www",
            },
            "tracking": {
                "creation_flow": "",
                "creation_point": "spotify.com",
                "referrer": "",
            },
            "recaptcha_token": captcha_token,
            "submission_id": self.submission_id,
            "flow_id": self.flow_id,
        }

    def _process_register(self, captcha_token: str) -> None:
        """Submit registration payload and handle embedded challenges.

        Args:
            captcha_token (str): Solved captcha token.

        Raises:
            GeneratorError: If registration fails or encounters a challenge.
        """
        payload = self._build_payload(captcha_token)
        response = self._post_request(self.CREATE_ACCOUNT_URL, payload)

        if "challenge" in response:
            self.cfg.logger.attempt("Encountered Embedded Challenge. Defeating...")
            AccountChallenge(self.client, response, self.cfg).defeat_challenge()

    def register(self) -> None:
        """Create a Spotify account.

        Steps:
            1. Retrieve session.
            2. Solve captcha using configured solver.
            3. Submit registration payload.
            4. Handle embedded challenges.
            5. Save account data

        Raises:
            GeneratorError: If solver is not set or any step fails.
        """
        self._get_session()
        if self.cfg.solver is None:
            raise GeneratorError("Solver not set")

        captcha_token = self.cfg.solver.solve_captcha(
            self.SIGNUP_URL,
            self.SITE_KEY,
            "website/signup/submit_email",
            "v3",
        )
        self._process_register(captcha_token)

        if self.cfg.saver:
            try:
                account_data = {
                    "identifier": self.email,
                    "password": self.password,
                    "cookies": self.client.cookies.get_dict(),
                }
                self.cfg.saver.save([account_data])
                self.cfg.logger.info(f"Account {self.email} saved successfully.")
            except Exception as e:
                self.cfg.logger.error(f"Failed to save account {self.email}: {e}")


class AccountChallenge:
    """
    Handles embedded challenges during Spotify account creation.

    Attributes:
        client (TLSClient): HTTP client.
        raw (Dict[str, Any]): Raw challenge response.
        session_id (str): Challenge session ID.
        cfg (Config): Configuration object.
        challenge_url (Optional[str]): URL of embedded challenge.
    """

    __slots__ = ("client", "raw", "session_id", "cfg", "challenge_url")

    def __init__(
        self, client: TLSClient, raw_response: Dict[str, Any], cfg: Config
    ) -> None:
        """Initialize AccountChallenge handler.

        Args:
            client (TLSClient): HTTP client.
            raw_response (Dict[str, Any]): Raw challenge response.
            cfg (Config): Configuration object.
        """
        self.client = client
        self.raw = raw_response
        self.session_id = parse_json_string(
            json.dumps(raw_response, separators=(",", ":")), "session_id"
        )
        self.cfg = cfg
        self.challenge_url: Optional[str] = None

    def _get_session(self) -> None:
        """Retrieve challenge session and extract challenge URL.

        Raises:
            GeneratorError: If challenge session cannot be retrieved.
        """
        url = "https://challenge.spotify.com/api/v1/get-session"
        payload = {"session_id": self.session_id}
        response = self.client.post(url, json=payload)
        if response.fail:
            raise GeneratorError(
                "Could not get challenge session", error=response.error.string
            )

        self.challenge_url = parse_json_string(
            json.dumps(response.response, separators=(",", ":")), "url"
        )

    def _submit_challenge(self, token: str) -> None:
        """Submit solved captcha token to challenge endpoint.

        Args:
            token (str): Captcha solution token.

        Raises:
            GeneratorError: If submission fails.
        """
        session_id = self.challenge_url.split("c/")[1].split("/")[0]
        challenge_id = self.challenge_url.split(session_id + "/")[1].split("/")[0]
        url = "https://challenge.spotify.com/api/v1/invoke-challenge-command"
        payload = {
            "session_id": session_id,
            "challenge_id": challenge_id,
            "recaptcha_challenge_v1": {"solve": {"recaptcha_token": token}},
        }
        headers = {
            "X-Cloud-Trace-Context": "000000000000000004ec7cfe60aa92b5/8088460714428896449;o=1"
        }
        resp = self.client.post(url, json=payload, headers=headers)
        if resp.fail:
            raise GeneratorError("Could not submit challenge", error=resp.error.string)

    def _complete_challenge(self) -> None:
        """Complete account creation after challenge submission.

        Raises:
            GeneratorError: If completion fails.
        """
        url = (
            "https://spclient.wg.spotify.com/signup/public/v2/account/complete-creation"
        )
        payload = {"session_id": self.session_id}
        resp = self.client.post(url, json=payload)
        if resp.fail:
            raise GeneratorError(
                "Could not complete challenge", error=resp.error.string
            )
        if "success" not in resp.response:
            raise GeneratorError("Could not complete challenge", error=resp.response)

    def defeat_challenge(self) -> None:
        """Execute full embedded challenge workflow.

        Steps:
            1. Retrieve challenge session.
            2. Solve captcha using configured solver.
            3. Submit challenge.
            4. Complete account creation.

        Raises:
            GeneratorError: If solver not set or any step fails.
        """
        self._get_session()
        if self.cfg.solver is None:
            raise GeneratorError("Solver not set")

        token = self.cfg.solver.solve_captcha(
            self.challenge_url,
            "6LeO36obAAAAALSBZrY6RYM1hcAY7RLvpDDcJLy3",
            "challenge",
            "v2",
        )
        self._submit_challenge(token)
        self._complete_challenge()
        self.cfg.logger.info("Successfully defeated challenge. Account created.")

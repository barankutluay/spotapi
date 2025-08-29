import time
import uuid
from typing import Optional

from spotapi.spotapi_exceptions import PasswordError
from spotapi.spotapi_types.annotations import enforce
from spotapi.spotapi_types.data import Config
from spotapi.spotapi_utils.strings import parse_json_string

__all__ = ["Password", "PasswordError"]


@enforce
class Password:
    """
    Handles Spotify password recovery.

    This class manages session retrieval, captcha solving, and
    password reset requests.

    Attributes:
        solver: Captcha solver instance from configuration.
        client: HTTP client from configuration.
        logger: Logger from configuration.
        identifier_credentials (str): Email or username for recovery.
        csrf (Optional[str]): CSRF token for requests.
        flow_id (Optional[str]): Unique flow identifier.

    Raises:
        ValueError: If neither email nor username is provided.
        PasswordError: If session retrieval fails.
        PasswordError: If captcha solving fails.
        PasswordError: If password reset submission fails.
    """

    __slots__ = (
        "solver",
        "client",
        "logger",
        "identifier_credentials",
        "csrf",
        "flow_id",
    )

    PASSWORD_RESET_URL = "https://accounts.spotify.com/en/password-reset"
    RECOVERY_API_URL = "https://accounts.spotify.com/api/password/recovery"
    SITE_KEY = "6LfCVLAUAAAAALFwwRnnCJ12DalriUGbj8FW_J39"

    def __init__(
        self,
        cfg: Config,
        *,
        email: Optional[str] = None,
        username: Optional[str] = None,
    ) -> None:
        """
        Initialize Password recovery handler.

        Args:
            cfg (Config): Configuration containing solver, client, and logger.
            email (Optional[str]): Email address for recovery.
            username (Optional[str]): Username for recovery.

        Raises:
            ValueError: If neither email nor username is provided.
        """
        self.solver = cfg.solver
        self.client = cfg.client
        self.logger = cfg.logger

        self.identifier_credentials: Optional[str] = username or email
        if not self.identifier_credentials:
            raise ValueError("Must provide an email or username")

        self.csrf: Optional[str] = None
        self.flow_id: Optional[str] = None

    def _get_session(self) -> None:
        """
        Retrieve password reset session and CSRF token.

        Raises:
            PasswordError: If session retrieval fails.
        """
        resp = self.client.get(self.PASSWORD_RESET_URL)
        if resp.fail:
            raise PasswordError("Could not get session", error=resp.error.string)

        self.csrf = parse_json_string(resp.response, "csrf")
        self.flow_id = str(uuid.uuid4())

    def _reset_password(self, token: str) -> None:
        """
        Submit password recovery request with solved captcha token.

        Args:
            token (str): Solved captcha token.

        Raises:
            PasswordError: If password reset submission fails.
        """
        payload = {
            "captcha": token,
            "emailOrUsername": self.identifier_credentials,
            "flowId": self.flow_id,
        }
        headers = {"X-Csrf-Token": self.csrf}

        resp = self.client.post(self.RECOVERY_API_URL, data=payload, headers=headers)
        if resp.fail:
            raise PasswordError("Could not reset password", error=resp.error.string)

    def reset(self) -> None:
        """
        Perform full password recovery process.

        Steps:
            1. Retrieve session.
            2. Solve captcha using configured solver.
            3. Submit recovery request.

        Raises:
            PasswordError: If captcha solver is not set, fails to solve captcha,
                           or password reset submission fails.
        """
        self._get_session()
        start_time = time.time()
        self.logger.attempt("Solving captcha...")

        if self.solver is None:
            raise PasswordError("Solver not set")

        captcha_response = self.solver.solve_captcha(
            self.PASSWORD_RESET_URL,
            self.SITE_KEY,
            "password_reset_web/recovery",
            "v3",
        )
        if not captcha_response:
            raise PasswordError("Could not solve captcha")

        self.logger.info(
            "Solved Captcha", time_taken=f"{int(time.time() - start_time)}s"
        )
        self._reset_password(captcha_response)
        self.logger.info(
            "Successfully reset password",
            time_taken=f"{int(time.time() - start_time)}s",
        )

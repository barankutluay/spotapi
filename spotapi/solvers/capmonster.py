"""
Capmonster API solver implementation.
Provides methods to create, harvest, and solve CAPTCHA tasks using the Capmonster service.
"""

from __future__ import annotations

import time
from typing import Literal

from spotapi.exceptions import CaptchaException, SolverError
from spotapi.http.request import StdClient

__all__ = ["Capmonster", "CaptchaException", "SolverError"]


class Capmonster:
    """
    Standard implementation of the Capmonster API.

    Attributes:
        api_key (str): Your Capmonster API key.
        client (StdClient): The HTTP client instance to use.
        proxy (str | None): Proxy is not supported with Capmonster (kept for interface conformity).
        retries (int): Number of retries when polling for task results.
    """

    __slots__ = ("api_key", "client", "proxy", "retries")
    BaseURL = "https://api.capmonster.cloud/"

    def __init__(
        self,
        api_key: str,
        client: StdClient = StdClient(3),
        *,
        retries: int = 120,
        proxy: str | None = None,
    ) -> None:
        """Initialize the Capmonster solver.

        Args:
            api_key (str): Your Capmonster API key.
            client (StdClient, optional): HTTP client instance. Defaults to StdClient(3).
            retries (int, optional): Maximum retries when harvesting a task. Defaults to 120.
            proxy (str | None, optional): Proxy (not supported). Defaults to None.

        Raises:
            CaptchaException: If proxy is provided (not supported).
        """
        self.api_key = api_key
        self.client = client
        self.proxy = proxy

        if self.proxy:
            raise CaptchaException("Only Proxyless mode is supported with Capmonster.")

        self.retries = retries
        self.client.authenticate = lambda kwargs: self._auth_rule(kwargs)

    def _auth_rule(self, kwargs: dict) -> dict:
        """Inject authentication credentials into the request payload.

        Args:
            kwargs (dict): Request kwargs.

        Returns:
            dict: Updated kwargs with API key.
        """
        if "json" not in kwargs:
            kwargs["json"] = {}
        kwargs["json"]["clientKey"] = self.api_key
        return kwargs

    def get_balance(self) -> float | None:
        """Retrieve the account balance from Capmonster.

        Returns:
            float | None: Account balance.

        Raises:
            CaptchaException: If balance retrieval fails.
        """
        endpoint = self.BaseURL + "getBalance"
        request = self.client.post(endpoint, authenticate=True)

        if request.fail:
            raise CaptchaException(
                "Could not retrieve balance.", error=request.error.string
            )

        resp = request.response
        if int(resp["errorId"]) != 0:
            raise CaptchaException(
                "Could not retrieve balance.", error=resp["errorCode"]
            )

        return resp["balance"]

    def _create_task(
        self,
        url: str,
        site_key: str,
        action: str,
        task: Literal["v2", "v3"],
        proxy: str | None = None,
    ) -> str:
        """Create a CAPTCHA solving task.

        Args:
            url (str): Target website URL.
            site_key (str): reCAPTCHA site key.
            action (str): Page action.
            task (Literal["v2", "v3"]): CAPTCHA type.
            proxy (str | None, optional): Proxy (unsupported for Capmonster).

        Returns:
            str: Task ID.

        Raises:
            CaptchaException: If task creation fails.
        """
        endpoint = self.BaseURL + "createTask"
        task_type = (
            "ReCaptcha{}EnterpriseTask"
            if proxy
            else "ReCaptcha{}EnterpriseTaskProxyLess"
        ).format(task.upper())

        payload = {
            "task": {
                "type": task_type,
                "websiteURL": url,
                "websiteKey": site_key,
                "pageAction": action,
            },
        }

        if proxy:
            payload["task"]["proxy"] = proxy

        request = self.client.post(endpoint, authenticate=True, json=payload)

        if request.fail:
            raise CaptchaException("Could not create task.", error=request.error.string)

        resp = request.response
        if int(resp["errorId"]) != 0:
            raise CaptchaException("Could not create task.", error=resp["errorCode"])

        return str(resp["taskId"])

    def _harvest_task(self, task_id: str, retries: int) -> str:
        """Poll Capmonster until task is solved or retries are exhausted.

        Args:
            task_id (str): ID of the created task.
            retries (int): Maximum retries before failure.

        Returns:
            str: Captcha solution (gRecaptchaResponse).

        Raises:
            CaptchaException: If Capmonster returns an error.
            SolverError: If retries are exhausted without solution.
        """
        for _ in range(retries):
            payload = {"taskId": task_id}
            endpoint = self.BaseURL + "getTaskResult"

            request = self.client.post(endpoint, authenticate=True, json=payload)

            if request.fail:
                raise CaptchaException(
                    "Could not get task result", error=request.error.string
                )

            resp = request.response
            if int(resp["errorId"]) != 0:
                raise CaptchaException(
                    "Could not get task result.", error=resp["errorCode"]
                )

            if resp["status"] == "ready":
                return str(resp["solution"]["gRecaptchaResponse"])

            time.sleep(1)

        raise SolverError("Failed to solve captcha.", error="Max retries reached")

    def solve_captcha(
        self,
        url: str,
        site_key: str,
        action: str,
        task: Literal["v2", "v3"],
    ) -> str:
        """Solve a CAPTCHA using Capmonster.

        Args:
            url (str): Target website URL.
            site_key (str): reCAPTCHA site key.
            action (str): Page action.
            task (Literal["v2", "v3"]): CAPTCHA type.

        Returns:
            str: Captcha solution token.

        Raises:
            CaptchaException: If task creation or result fetching fails.
            SolverError: If retries are exhausted without solution.
        """
        task_id = self._create_task(url, site_key, action, task, self.proxy)
        return self._harvest_task(task_id, self.retries)

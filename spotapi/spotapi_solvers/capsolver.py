from __future__ import annotations

import time
from typing import Any, Dict, Literal

from spotapi.spotapi_exceptions import CaptchaException, SolverError
from spotapi.spotapi_http.request import StdClient

__all__ = ["Capsolver", "CaptchaException", "SolverError"]


class Capsolver:
    """
    Standard implementation of the Capsolver API.

    Parameters
    ----------
    api_key : str
        Your capsolver API key.
    client : StdClient
        The http client to use.
    retries : int
        The number of retries to attempt.
    proxy : str | None
        The HTTP proxy to use. Must be in the format "username:password@host:port".
    """

    __slots__ = ("api_key", "client", "proxy", "retries")

    BaseURL = "https://api.capsolver.com/"

    def __init__(
        self,
        api_key: str,
        client: StdClient = StdClient(3),
        *,
        retries: int = 120,
        proxy: str | None = None,
    ) -> None:
        self.api_key = api_key
        self.client = client
        self.proxy = proxy
        self.retries = retries
        self.client.authenticate = lambda kwargs: self._auth_rule(kwargs)

    def _auth_rule(self, kwargs: dict) -> dict:
        kwargs.setdefault("json", {})
        kwargs["json"]["clientKey"] = self.api_key
        return kwargs

    def get_balance(self) -> float | None:
        endpoint = self.BaseURL + "getBalance"
        request = self.client.post(endpoint, authenticate=True)

        if request.fail:
            raise CaptchaException(
                "Could not retrieve balance.", error=request.error.string
            )

        resp = request.response
        if int(resp["errorId"]) != 0:
            raise CaptchaException(
                "Could not retrieve balance.", error=resp["errorDescription"]
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
        endpoint = self.BaseURL + "createTask"
        task_type = (
            "ReCaptcha{}EnterpriseTask"
            if proxy
            else "ReCaptcha{}EnterpriseTaskProxyLess"
        ).format(task.upper())

        payload: Dict[str, Dict[str, Any]] = {
            "task": {
                "type": task_type,
                "websiteURL": url,
                "websiteKey": site_key,
                "pageAction": action,
            }
        }

        if task == "v2":
            payload["task"]["isInvisible"] = True
        if proxy:
            payload["task"]["proxy"] = proxy

        request = self.client.post(endpoint, authenticate=True, json=payload)

        if request.fail:
            raise CaptchaException("Could not create task.", error=request.error.string)

        resp = request.response
        if int(resp["errorId"]) != 0:
            raise CaptchaException(
                "Could not create task.", error=resp["errorDescription"]
            )

        return str(resp["taskId"])

    def _harvest_task(self, task_id: str, retries: int) -> str:
        endpoint = self.BaseURL + "getTaskResult"
        for _ in range(retries):
            request = self.client.post(
                endpoint, authenticate=True, json={"taskId": task_id}
            )

            if request.fail:
                raise CaptchaException(
                    "Could not get task result.", error=request.error.string
                )

            resp = request.response
            if int(resp["errorId"]) != 0:
                raise CaptchaException(
                    "Could not get task result.", error=resp["errorDescription"]
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
        task_id = self._create_task(url, site_key, action, task, self.proxy)
        return self._harvest_task(task_id, self.retries)

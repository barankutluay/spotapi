from __future__ import annotations

import atexit
import json
from typing import Any, Callable, Dict, Type

import requests
from tls_client import Session
from tls_client.exceptions import TLSClientExeption
from tls_client.response import Response as TLSResponse
from tls_client.settings import ClientIdentifiers

from spotapi.exceptions import ParentException, RequestError
from spotapi.http.data import Response

__all__ = [
    "StdClient",
    "TLSClient",
    "ClientIdentifiers",
    "ParentException",
    "RequestError",
    "Response",
]


class StdClient:
    """
    Standard HTTP client wrapped around the requests library.
    """

    __slots__ = ("_client", "auto_retries", "authenticate")

    def __init__(
        self,
        auto_retries: int = 0,
        auth_rule: Callable[[Dict[Any, Any]], Dict[Any, Any]] | None = None,
    ) -> None:
        self._client = requests.Session()
        self.auto_retries = auto_retries + 1
        self.authenticate = auth_rule
        atexit.register(self._client.close)

    def __call__(self, method: str, url: str, **kwargs) -> requests.Response | None:
        return self.build_request(method, url, **kwargs)

    def build_request(
        self, method: str, url: str | bytes, **kwargs
    ) -> requests.Response | None:
        if isinstance(url, (bytes, memoryview)):
            url = (
                url.tobytes().decode("utf-8")
                if isinstance(url, memoryview)
                else url.decode("utf-8")
            )

        err = "Unknown"
        for _ in range(self.auto_retries):
            try:
                return self._client.request(method.upper(), url, **kwargs)
            except Exception as e:
                err = str(e)
                continue

        raise RequestError("Failed to complete request.", error=err)

    def parse_response(self, response: requests.Response) -> Response:
        body: str | Dict[Any, Any] | None = response.text
        headers = {k.lower(): v for k, v in response.headers.items()}

        if "application/json" in headers.get("content-type", ""):
            try:
                body = response.json()
            except ValueError:
                pass

        return Response(status_code=response.status_code, response=body, raw=response)

    def request(
        self, method: str, url: str | bytes, *, authenticate: bool = False, **kwargs
    ) -> Response:
        if authenticate and self.authenticate:
            kwargs = self.authenticate(kwargs)

        response = self.build_request(method, url, **kwargs)
        if response is None:
            raise RequestError("Request kept failing after retries.")

        return self.parse_response(response)

    def post(
        self, url: str | bytes, *, authenticate: bool = False, **kwargs
    ) -> Response:
        return self.request("POST", url, authenticate=authenticate, **kwargs)

    def get(
        self, url: str | bytes, *, authenticate: bool = False, **kwargs
    ) -> Response:
        return self.request("GET", url, authenticate=authenticate, **kwargs)

    def put(
        self, url: str | bytes, *, authenticate: bool = False, **kwargs
    ) -> Response:
        return self.request("PUT", url, authenticate=authenticate, **kwargs)


class TLSClient(Session):
    """
    TLS HTTP client wrapped around the tls_client library.
    Fully undetected by Spotify.com.
    """

    def __init__(
        self,
        profile: ClientIdentifiers,
        proxy: str,
        *,
        auto_retries: int = 0,
        auth_rule: Callable[[Dict[Any, Any]], Dict[Any, Any]] | None = None,
    ) -> None:
        super().__init__(client_identifier=profile, random_tls_extension_order=True)

        if proxy:
            self.proxies = {"http": f"http://{proxy}", "https": f"http://{proxy}"}

        self.auto_retries = auto_retries + 1
        self.authenticate = auth_rule
        self.fail_exception: Type[ParentException] | None = None
        atexit.register(self.close)

    def __call__(self, method: str, url: str, **kwargs) -> TLSResponse | None:
        return self.build_request(method, url, **kwargs)

    def build_request(
        self, method: str, url: str | bytes, **kwargs
    ) -> TLSResponse | None:
        if isinstance(url, (bytes, memoryview)):
            url = (
                url.tobytes().decode("utf-8")
                if isinstance(url, memoryview)
                else url.decode("utf-8")
            )

        err = "Unknown"
        for _ in range(self.auto_retries):
            try:
                return self.execute_request(method.upper(), url, **kwargs)
            except TLSClientExeption as e:
                err = str(e)
                continue

        raise RequestError("Failed to complete request.", error=err)

    def parse_response(
        self, response: TLSResponse, method: str, danger: bool
    ) -> Response:
        body: str | Dict[Any, Any] | None = response.text
        headers = {k.lower(): v for k, v in response.headers.items()}

        json_encoded = "application/json" in headers.get("content-type", "")
        is_dict = True

        try:
            json.loads(body)  # type: ignore
        except json.JSONDecodeError:
            is_dict = False

        if json_encoded or is_dict:
            json_formatted = response.json()
            body = json_formatted if isinstance(json_formatted, Dict) else body

        if not body:
            body = None

        assert response.status_code is not None, "Status Code is None"

        resp = Response(
            status_code=int(response.status_code), response=body, raw=response
        )

        if danger and self.fail_exception and resp.fail:
            raise self.fail_exception(
                f"Could not {method} {str(response.url).split('?')[0]}. "
                f"Status Code: {resp.status_code}",
                "Request Failed.",
            )

        return resp

    def get(
        self, url: str | bytes, *, authenticate: bool = False, **kwargs
    ) -> Response:
        if authenticate and self.authenticate:
            kwargs = self.authenticate(kwargs)

        response = self.build_request("GET", url, allow_redirects=True, **kwargs)
        if response is None:
            raise TLSClientExeption("Request kept failing after retries.")

        return self.parse_response(response, "GET", True)

    def post(
        self,
        url: str | bytes,
        *,
        authenticate: bool = False,
        danger: bool = False,
        **kwargs,
    ) -> Response:
        if authenticate and self.authenticate:
            kwargs = self.authenticate(kwargs)

        response = self.build_request("POST", url, allow_redirects=True, **kwargs)
        if response is None:
            raise TLSClientExeption("Request kept failing after retries.")

        return self.parse_response(response, "POST", danger)

    def put(
        self,
        url: str | bytes,
        *,
        authenticate: bool = False,
        danger: bool = False,
        **kwargs,
    ) -> Response:
        if authenticate and self.authenticate:
            kwargs = self.authenticate(kwargs)

        response = self.build_request("PUT", url, allow_redirects=True, **kwargs)
        if response is None:
            raise TLSClientExeption("Request kept failing after retries.")

        return self.parse_response(response, "PUT", danger)

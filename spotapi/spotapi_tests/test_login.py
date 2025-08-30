import json
import logging
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Generator
from unittest.mock import MagicMock

import pytest
from requests.cookies import RequestsCookieJar
from rich.console import Console
from rich.table import Table

from login import Login, LoginChallenge, LoginError

# --------------------------------------------------------------------------------------
# Rich Console & Markdown Report
# --------------------------------------------------------------------------------------
console: Console = Console(record=True)
REPORT_PATH: Path = Path(f"./spotapi_tests/reports_{Path(__file__).stem}.md")
REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)


def save_report() -> None:
    console.save_text(str(REPORT_PATH))


def log_table(title: str, data: Dict[str, Any]) -> None:
    table: Table = Table(title=title)
    table.add_column("Metric", style="cyan", justify="left")
    table.add_column("Value", style="magenta", justify="right")
    for k, v in data.items():
        table.add_row(str(k), str(v))
    console.print(table)
    with REPORT_PATH.open("a", encoding="utf-8") as f:
        f.write(f"### {title}\n\n")
        f.write("| Metric | Value |\n|--------|-------|\n")
        for k, v in data.items():
            f.write(f"| {k} | {v} |\n")
        f.write("\n")


def log_message(msg: str) -> None:
    console.print(msg)
    with REPORT_PATH.open("a", encoding="utf-8") as f:
        clean: str = re.sub(r"\[.*?\]", "", msg)
        f.write(f"{clean}\n\n")


# --------------------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------------------
@pytest.fixture
def mock_cfg() -> Generator[MagicMock, None, None]:
    client = MagicMock()
    solver = MagicMock()
    saver = MagicMock()
    logger = MagicMock()
    yield MagicMock(client=client, solver=solver, saver=saver, logger=logger)


@pytest.fixture(scope="session", autouse=True)
def clear_report():
    if REPORT_PATH.exists():
        REPORT_PATH.unlink()
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    yield


# --------------------------------------------------------------------------------------
# Integration Tests
# --------------------------------------------------------------------------------------
def test_login_integration_flow(mock_cfg: MagicMock) -> None:
    mock_get_resp = SimpleNamespace(
        fail=False,
        response='{"flowCtx":"flow_integration"}',
        raw=SimpleNamespace(
            cookies=SimpleNamespace(
                get=lambda k: "csrf_integration" if k == "sp_sso_csrf_token" else None
            )
        ),
    )
    mock_cfg.client.get.return_value = mock_get_resp
    mock_post_resp = SimpleNamespace(
        fail=False,
        response={"result": "ok"},
        raw=SimpleNamespace(
            cookies=SimpleNamespace(
                get=lambda k: "csrf_integration" if k == "sp_sso_csrf_token" else None
            )
        ),
    )
    mock_cfg.client.post.return_value = mock_post_resp
    mock_cfg.solver.solve_captcha.return_value = "captcha_integration"

    login = Login(
        mock_cfg, password="integration_pass", email="integration@example.com"
    )
    login.login()

    assert login.logged_in
    assert login.csrf_token == "csrf_integration"
    log_message("Integration flow: Login.login() executed successfully.")


# --------------------------------------------------------------------------------------
# Unit Tests
# --------------------------------------------------------------------------------------
def test_login_initialization(mock_cfg: MagicMock) -> None:
    login = Login(mock_cfg, password="password123", email="user@example.com")
    log_table(
        "Login Initialization",
        {
            "Identifier": login.identifier_credentials,
            "Password": login.password,
            "Logged In": login.logged_in,
        },
    )
    assert login.identifier_credentials == "user@example.com"
    assert login.password == "password123"
    assert not login.logged_in


def test_login_from_cookies_sets_logged_in(mock_cfg: MagicMock) -> None:
    jar = RequestsCookieJar()
    cookies = {"session": "abc123"}
    for k, v in cookies.items():
        jar.set(k, v, domain=".spotify.com", path="/")
    mock_cfg.client.cookies = jar
    dump = {"identifier": "user@example.com", "password": "pass", "cookies": cookies}
    instance = Login.from_cookies(dump, mock_cfg)
    log_table("Login from_cookies", {"Logged In": instance.logged_in})
    assert instance.logged_in
    assert instance.client.cookies.get_dict() == cookies


def test_login_from_saver_calls_load_and_from_cookies(mock_cfg: MagicMock) -> None:
    mock_saver = MagicMock()
    mock_saver.load.return_value = {
        "identifier": "user@example.com",
        "password": "pass",
        "cookies": {"session": "xyz"},
    }
    instance = Login.from_saver(mock_saver, mock_cfg, "user@example.com")
    log_message("Login from_saver loaded successfully.")
    assert instance.logged_in
    mock_saver.load.assert_called_once_with(query={"identifier": "user@example.com"})


def test_password_payload_and_submit_password(mock_cfg: MagicMock) -> None:
    login = Login(mock_cfg, password="pass123", email="user@example.com")
    login.flow_id = "flow123"
    login.csrf_token = "csrf"
    resp = SimpleNamespace(
        fail=False,
        response={"result": "ok"},
        raw=SimpleNamespace(cookies={"get": lambda k: "csrf"}),
    )
    mock_cfg.client.post.return_value = resp
    mock_cfg.client.get.return_value = resp
    payload = login._password_payload("captcha-token")
    assert "captcha-token" in payload
    login._submit_password("captcha-token")
    log_message("_submit_password executed successfully.")


def test_login_handles_solver_none(mock_cfg: MagicMock) -> None:
    login = Login(mock_cfg, password="pass", email="user@example.com")
    login.solver = None
    with pytest.raises(LoginError):
        login.login()
    log_message("Login raised LoginError due to missing solver.")


def test_login_error_handling(mock_cfg: MagicMock) -> None:
    login = Login(mock_cfg, password="pass", email="user@example.com")
    error_data = {"error": "errorInvalidCredentials"}
    with pytest.raises(LoginError):
        login.handle_login_error(error_data)
    log_message("handle_login_error raised LoginError as expected.")


def test_login_full_flow(mock_cfg: MagicMock) -> None:
    login = Login(mock_cfg, password="pass", email="user@example.com")
    login.solver.solve_captcha.return_value = "captcha123"
    mock_get_resp = SimpleNamespace(
        fail=False,
        response='{"flowCtx":"flow123"}',
        raw=SimpleNamespace(cookies={"get": lambda k: "csrf"}),
    )
    mock_post_resp = SimpleNamespace(
        fail=False,
        response={"result": "ok"},
        raw=SimpleNamespace(cookies={"get": lambda k: "csrf"}),
    )
    mock_cfg.client.get.return_value = mock_get_resp
    mock_cfg.client.post.return_value = mock_post_resp
    login.login()
    log_message("Full login flow executed successfully.")
    assert login.logged_in


# --------------------------------------------------------------------------------------
# LoginChallenge Tests
# --------------------------------------------------------------------------------------
def test_challenge_payload_submission(mock_cfg: MagicMock) -> None:
    login = Login(mock_cfg, password="pass", email="user@example.com")
    dump = {"data": {"redirect_url": "https://challenge.spotify.com/c/sess/chal/"}}
    challenge = LoginChallenge(login, dump)
    login.solver.solve_captcha.return_value = "token123"
    resp = SimpleNamespace(
        fail=False,
        response={"completed": {"hash": "h", "interaction_reference": "r"}},
        raw=None,
    )
    mock_cfg.client.post.return_value = resp
    challenge._submit_challenge()
    log_message("_submit_challenge executed successfully.")


def test_challenge_defeat_calls_all_steps(mock_cfg: MagicMock) -> None:
    login = Login(mock_cfg, password="pass", email="user@example.com")
    dump = {"data": {"redirect_url": "https://challenge.spotify.com/c/sess/chal/"}}
    challenge = LoginChallenge(login, dump)
    mock_post_resp = SimpleNamespace(
        fail=False,
        response={"completed": {"hash": "h", "interaction_reference": "r"}},
        raw=None,
    )
    mock_cfg.client.get.return_value.fail = False
    mock_cfg.client.post.return_value = mock_post_resp
    challenge.defeat()
    assert challenge.interaction_hash == "h"
    assert challenge.interaction_reference == "r"
    log_message("LoginChallenge.defeat executed successfully.")

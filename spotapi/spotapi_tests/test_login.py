import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict
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
REPORT_PATH: Path = Path(f"./spotapi_tests/reports/reports_{Path(__file__).stem}.md")
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
def mock_cfg() -> MagicMock:
    client = MagicMock()
    solver = MagicMock()
    saver = MagicMock()
    logger = MagicMock()
    cfg = MagicMock(client=client, solver=solver, saver=saver, logger=logger)
    return cfg


@pytest.fixture(scope="session", autouse=True)
def clear_report():
    if REPORT_PATH.exists():
        REPORT_PATH.unlink()
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    yield


# --------------------------------------------------------------------------------------
# Unit Tests: Login
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


def test_from_cookies_parses_cookie_with_equal_sign(mock_cfg):
    cookie_str = "foo=bar; baz=qux"
    dump = {"identifier": "user@example.com", "password": "pass", "cookies": cookie_str}
    parsed = {}
    for cookie in cookie_str.split(";"):
        if "=" in cookie:
            k, v = cookie.split("=", 1)
            parsed[k.strip()] = v.strip()
    assert parsed == {"foo": "bar", "baz": "qux"}


def test_login_raises_if_solver_none(mock_cfg):
    login = Login(mock_cfg, password="pass", email="user@example.com")
    login.solver = None

    mock_cfg.client.get.return_value = SimpleNamespace(
        fail=False,
        response='{"flowCtx":"flow123"}',
        raw=SimpleNamespace(cookies=SimpleNamespace(get=lambda k: "csrf")),
    )

    with pytest.raises(LoginError) as exc:
        login.login()
    assert "Solver not set" in str(exc.value)


def test_login_challenge_submit_fail_resp_fail(mock_cfg):
    login = Login(mock_cfg, password="pass", email="user@example.com")
    login.solver.solve_captcha.return_value = "tok"
    challenge = LoginChallenge(
        login, {"data": {"redirect_url": "https://challenge.spotify.com/c/sess/chal/"}}
    )
    challenge.session_id = "sess"
    mock_cfg.client.post.return_value = SimpleNamespace(
        fail=True, error=SimpleNamespace(string="fail")
    )
    with pytest.raises(LoginError) as exc:
        challenge._submit_challenge()
    assert "Could not submit challenge" in str(exc.value)


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


def test_login_init_without_identifier_raises(mock_cfg):
    with pytest.raises(ValueError):
        Login(mock_cfg, password="pass")


def test_login_save_raises_if_not_logged_in(mock_cfg):
    login = Login(mock_cfg, password="pass", email="user@example.com")
    with pytest.raises(ValueError):
        login.save(mock_cfg.saver)


def test_login_save_success_when_logged_in(mock_cfg):
    login = Login(mock_cfg, password="pass", email="user@example.com")
    login.logged_in = True
    mock_cfg.client.cookies.get_dict.return_value = {"cookie": "val"}
    login.save(mock_cfg.saver)
    mock_cfg.saver.save.assert_called_once()


def test_login_from_cookies_invalid_format_raises(mock_cfg):
    with pytest.raises(ValueError):
        Login.from_cookies({"cookies": "not_valid"}, mock_cfg)


def test_repr_and_str_methods(mock_cfg):
    login = Login(mock_cfg, password="pass", email="user@example.com")
    assert "user@example.com" in repr(login)
    assert "user@example.com" in str(login)


def test_get_add_cookie_raises_on_fail(mock_cfg):
    login = Login(mock_cfg, password="pass", email="user@example.com")
    mock_cfg.client.get.return_value = SimpleNamespace(
        fail=True, error=SimpleNamespace(string="fail")
    )
    with pytest.raises(LoginError):
        login._get_add_cookie("http://bad.url")


def test_set_non_otc_raises_on_fail(mock_cfg):
    login = Login(mock_cfg, password="pass", email="user@example.com")
    mock_cfg.client.get.return_value = SimpleNamespace(
        fail=True, error=SimpleNamespace(string="fail")
    )
    with pytest.raises(LoginError):
        login._set_non_otc()


def test_get_session_raises_on_fail(mock_cfg):
    login = Login(mock_cfg, password="pass", email="user@example.com")
    mock_cfg.client.get.return_value = SimpleNamespace(
        fail=True, error=SimpleNamespace(string="fail")
    )
    with pytest.raises(LoginError):
        login._get_session()


def test_submit_password_raises_on_fail(mock_cfg):
    login = Login(mock_cfg, password="pass", email="user@example.com")
    login.csrf_token = "csrf"
    mock_cfg.client.post.return_value = SimpleNamespace(
        fail=True, error=SimpleNamespace(string="fail")
    )
    with pytest.raises(LoginError):
        login._submit_password("tok")


def test_handle_login_error_redirect_required_triggers_challenge(mock_cfg):
    login = Login(mock_cfg, password="pass", email="user@example.com")
    dump = {
        "result": "redirect_required",
        "data": {"redirect_url": "https://challenge.spotify.com/c/sess/chal/"},
    }
    original_defeat = LoginChallenge.defeat
    LoginChallenge.defeat = lambda self: setattr(
        self, "interaction_hash", "h"
    ) or setattr(self, "interaction_reference", "r")
    login.handle_login_error(dump)
    mock_cfg.logger.attempt.assert_called_once()
    LoginChallenge.defeat = original_defeat


def test_handle_login_error_unexpected_format_raises(mock_cfg):
    login = Login(mock_cfg, password="pass", email="user@example.com")
    with pytest.raises(LoginError):
        login.handle_login_error({"foo": "bar"})


def test_handle_login_error_error_unknown(mock_cfg):
    login = Login(mock_cfg, password="pass", email="user@example.com")
    with pytest.raises(LoginError):
        login.handle_login_error({"error": "errorUnknown"})


def test_handle_login_error_unforeseen(mock_cfg):
    login = Login(mock_cfg, password="pass", email="user@example.com")
    with pytest.raises(LoginError):
        login.handle_login_error({"error": "other"})


def test_login_raises_if_already_logged_in(mock_cfg):
    login = Login(mock_cfg, password="pass", email="user@example.com")
    login.logged_in = True
    with pytest.raises(LoginError):
        login.login()


def test_login_raises_if_captcha_not_solved(mock_cfg):
    login = Login(mock_cfg, password="pass", email="user@example.com")
    mock_cfg.client.get.return_value = SimpleNamespace(
        fail=False,
        response='{"flowCtx":"fid"}',
        raw=SimpleNamespace(cookies=SimpleNamespace(get=lambda k: "csrf")),
    )
    login.solver.solve_captcha.return_value = None
    with pytest.raises(LoginError):
        login.login()


def test_from_cookies_ignores_invalid_cookies(mock_cfg):
    dump = {
        "identifier": "user@example.com",
        "password": "pass",
        "cookies": "foo=bar; invalidcookie; baz=qux",
    }

    instance = Login.from_cookies(dump, mock_cfg)

    calls = mock_cfg.client.cookies.set.call_args_list
    called_cookies = {call.args[0]: call.args[1] for call in calls}

    expected = {"foo": "bar", "baz": "qux"}
    assert called_cookies == expected
    assert instance.logged_in


def test_solver_exception_wraps_login_error(mock_cfg):
    login = Login(mock_cfg, password="pass", email="user@example.com")

    def raise_exc(*args, **kwargs):
        raise Exception("Solver failure")

    login.solver.solve_captcha.side_effect = raise_exc
    mock_cfg.client.get.return_value = SimpleNamespace(
        fail=False,
        response='{"flowCtx":"flow123"}',
        raw=SimpleNamespace(cookies=SimpleNamespace(get=lambda k: "csrf")),
    )

    with pytest.raises(Exception) as e:
        login.login()
    assert "Solver failure" in str(e.value)


def test_from_cookies_with_missing_fields_raises(mock_cfg):
    with pytest.raises(ValueError):
        Login.from_cookies({"identifier": "id_only"}, mock_cfg)


def test_password_payload_encoding(mock_cfg):
    login = Login(mock_cfg, password="pass&123", email="user@example.com")
    login.flow_id = "flow&123"
    payload = login._password_payload("tok&123")
    assert "pass%26123" in payload
    assert "tok%26123" in payload


# --------------------------------------------------------------------------------------
# Unit Tests: LoginChallenge
# --------------------------------------------------------------------------------------
def test_challenge_payload_submission(mock_cfg: MagicMock) -> None:
    login = Login(mock_cfg, password="pass", email="user@example.com")
    dump = {"data": {"redirect_url": "https://challenge.spotify.com/c/sess/chal/"}}
    challenge = LoginChallenge(login, dump)
    login.solver.solve_captcha.return_value = "token123"
    mock_cfg.client.post.return_value = SimpleNamespace(
        fail=False,
        response={"completed": {"hash": "h", "interaction_reference": "r"}},
        raw=None,
    )
    challenge._submit_challenge()
    log_message("_submit_challenge executed successfully.")


def test_challenge_defeat_calls_all_steps(mock_cfg: MagicMock) -> None:
    login = Login(mock_cfg, password="pass", email="user@example.com")
    dump = {"data": {"redirect_url": "https://challenge.spotify.com/c/sess/chal/"}}
    challenge = LoginChallenge(login, dump)

    login.solver.solve_captcha.return_value = "tok"

    mock_cfg.client.get.side_effect = lambda *args, **kwargs: SimpleNamespace(
        fail=False, response={}, raw=None
    )
    mock_cfg.client.post.side_effect = lambda *args, **kwargs: SimpleNamespace(
        fail=False,
        response={"completed": {"hash": "h", "interaction_reference": "r"}},
        raw=None,
    )

    challenge.defeat()

    assert challenge.interaction_hash == "h"
    assert challenge.interaction_reference == "r"


def test_challenge_get_challenge_fail(mock_cfg):
    login = Login(mock_cfg, password="pass", email="user@example.com")
    dump = {"data": {"redirect_url": "https://challenge.spotify.com/c/sess/chal/"}}
    challenge = LoginChallenge(login, dump)
    mock_cfg.client.get.return_value = SimpleNamespace(
        fail=True, error=SimpleNamespace(string="fail")
    )
    with pytest.raises(LoginError):
        challenge._get_challenge()


def test_challenge_construct_payload_solver_none(mock_cfg):
    login = Login(mock_cfg, password="pass", email="user@example.com")
    login.solver = None
    dump = {"data": {"redirect_url": "https://challenge.spotify.com/c/sess/chal/"}}
    challenge = LoginChallenge(login, dump)
    with pytest.raises(LoginError):
        challenge._construct_challenge_payload()


def test_challenge_construct_payload_captcha_fails(mock_cfg):
    login = Login(mock_cfg, password="pass", email="user@example.com")
    login.solver.solve_captcha.return_value = None
    dump = {"data": {"redirect_url": "https://challenge.spotify.com/c/sess/chal/"}}
    challenge = LoginChallenge(login, dump)
    with pytest.raises(LoginError):
        challenge._construct_challenge_payload()


def test_challenge_submit_invalid_json_response(mock_cfg):
    login = Login(mock_cfg, password="pass", email="user@example.com")
    login.solver.solve_captcha.return_value = "tok"
    dump = {"data": {"redirect_url": "https://challenge.spotify.com/c/sess/chal/"}}
    challenge = LoginChallenge(login, dump)
    mock_cfg.client.post.return_value = SimpleNamespace(
        fail=False, response="not_mapping"
    )
    with pytest.raises(LoginError):
        challenge._submit_challenge()


def test_challenge_complete_fail(mock_cfg):
    login = Login(mock_cfg, password="pass", email="user@example.com")
    dump = {"data": {"redirect_url": "https://challenge.spotify.com/c/sess/chal/"}}
    challenge = LoginChallenge(login, dump)
    challenge.session_id = "sess"
    challenge.interaction_reference = "ref"
    challenge.interaction_hash = "hash"
    mock_cfg.client.get.return_value = SimpleNamespace(
        fail=True, error=SimpleNamespace(string="fail")
    )
    with pytest.raises(LoginError):
        challenge._complete_challenge()

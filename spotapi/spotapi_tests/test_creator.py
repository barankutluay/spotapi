import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, Generator
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console
from rich.table import Table

from creator import AccountChallenge, Creator, GeneratorError

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
        f.write("| Metric | Value |\n")
        f.write("|--------|-------|\n")
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
    client: MagicMock = MagicMock()
    solver: MagicMock = MagicMock()
    saver: MagicMock = MagicMock()
    logger: MagicMock = MagicMock()
    yield MagicMock(client=client, solver=solver, saver=saver, logger=logger)


@pytest.fixture(scope="session", autouse=True)
def clear_report():
    if REPORT_PATH.exists():
        REPORT_PATH.unlink()
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    yield


# --------------------------------------------------------------------------------------
# Integration Test
# --------------------------------------------------------------------------------------
def test_register_integration_flow(mock_cfg: MagicMock) -> None:
    mock_cfg.client.get.return_value.fail = False
    mock_cfg.client.get.return_value.response = (
        '{"signupServiceAppKey":"key","spT":"inst","csrfToken":"csrf","flowId":"flow"}'
    )

    mock_cfg.solver.solve_captcha.return_value = "captcha-token"
    mock_cfg.client.post.return_value.fail = False
    mock_cfg.client.post.return_value.response = {"success": True}
    mock_cfg.saver.save.return_value = None

    creator = Creator(mock_cfg)
    creator.register()

    assert creator.api_key == "key"
    assert creator.installation_id == "inst"
    assert creator.csrf_token == "csrf"
    assert creator.flow_id == "flow"
    mock_cfg.solver.solve_captcha.assert_called_once_with(
        creator.SIGNUP_URL, creator.SITE_KEY, "website/signup/submit_email", "v3"
    )
    mock_cfg.client.post.assert_called()
    mock_cfg.saver.save.assert_called_once()
    mock_cfg.logger.info.assert_called()

    log_message("Integration flow: Creator.register() executed successfully.")


# --------------------------------------------------------------------------------------
# Unit Tests
# --------------------------------------------------------------------------------------
def test_creator_initialization_defaults(
    mock_cfg: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO):
        creator: Creator = Creator(mock_cfg)
        log_table(
            "Creator Defaults",
            {
                "Email": creator.email,
                "Password length": len(creator.password),
                "Display Name": creator.display_name,
                "Birthdate": creator.birthdate,
                "Submission ID": creator.submission_id,
            },
        )
        assert "@" in creator.email
        assert len(creator.password) >= 10
        assert creator.display_name
        assert len(creator.birthdate.split("-")) == 3


def test_get_session_success(mock_cfg: MagicMock) -> None:
    mock_cfg.client.get.return_value.fail = False
    mock_cfg.client.get.return_value.response = (
        '{"signupServiceAppKey":"key","spT":"inst","csrfToken":"csrf","flowId":"flow"}'
    )
    creator: Creator = Creator(mock_cfg)
    creator._get_session()
    log_table(
        "Session Tokens",
        {
            "api_key": creator.api_key,
            "installation_id": creator.installation_id,
            "csrf_token": creator.csrf_token,
            "flow_id": creator.flow_id,
        },
    )
    assert creator.api_key == "key"
    assert creator.installation_id == "inst"
    assert creator.csrf_token == "csrf"
    assert creator.flow_id == "flow"


def test_get_session_failure(mock_cfg: MagicMock) -> None:
    mock_cfg.client.get.return_value.fail = True
    mock_cfg.client.get.return_value.error.string = "bad error"
    creator: Creator = Creator(mock_cfg)
    with pytest.raises(GeneratorError):
        creator._get_session()
    log_message("Session retrieval failed as expected.")


def test_build_payload_structure(mock_cfg: MagicMock) -> None:
    creator: Creator = Creator(mock_cfg)
    creator.api_key, creator.installation_id, creator.flow_id = "k", "i", "f"
    payload: Dict[str, Any] = creator._build_payload("captcha-token")
    log_table("Payload Keys", {k: type(v).__name__ for k, v in payload.items()})
    assert payload["recaptcha_token"] == "captcha-token"
    assert payload["client_info"]["api_key"] == "k"


def test_process_register_handles_challenge(mock_cfg: MagicMock) -> None:
    creator: Creator = Creator(mock_cfg)
    creator.api_key, creator.installation_id, creator.flow_id = "a", "b", "c"
    mock_cfg.client.post.return_value.fail = False
    mock_cfg.client.post.return_value.response = {"challenge": True}
    with patch("creator.AccountChallenge") as MockChallenge:
        creator._process_register("captcha123")
        MockChallenge.assert_called_once()
    log_message("Challenge handled successfully.")


def test_register_without_solver_raises(mock_cfg: MagicMock) -> None:
    mock_cfg.solver = None
    creator: Creator = Creator(mock_cfg)
    with pytest.raises(GeneratorError):
        creator.register()
    log_message("Register failed as solver is missing.")


def test_register_full_flow(mock_cfg: MagicMock) -> None:
    creator: Creator = Creator(mock_cfg)
    mock_cfg.client.get.return_value.fail = False
    mock_cfg.client.get.return_value.response = (
        '{"signupServiceAppKey":"key","spT":"inst","csrfToken":"csrf","flowId":"flow"}'
    )
    mock_cfg.solver.solve_captcha.return_value = "token123"
    mock_cfg.client.post.return_value.fail = False
    mock_cfg.client.post.return_value.response = {"success": True}
    mock_cfg.saver.save.return_value = None

    creator.register()

    mock_cfg.solver.solve_captcha.assert_called_once()
    mock_cfg.client.post.assert_called()
    mock_cfg.saver.save.assert_called_once()
    mock_cfg.logger.info.assert_called()
    log_message("Register full flow executed successfully.")


def test_post_request_failure(mock_cfg: MagicMock) -> None:
    creator: Creator = Creator(mock_cfg)
    mock_cfg.client.post.return_value.fail = True
    mock_cfg.client.post.return_value.error.string = "fail"
    with pytest.raises(GeneratorError):
        creator._post_request("url", {"payload": 1})
    log_message("_post_request failure raised GeneratorError as expected.")


# --------------------------------------------------------------------------------------
# AccountChallenge Tests
# --------------------------------------------------------------------------------------
def test_account_challenge_flow(mock_cfg: MagicMock) -> None:
    raw_response: Dict[str, Any] = {"session_id": "sess123"}
    challenge: AccountChallenge = AccountChallenge(
        mock_cfg.client, raw_response, mock_cfg
    )
    challenge.challenge_url = "https://challenge.spotify.com/c/sess123/chal456/"
    mock_cfg.client.post.return_value.fail = False
    mock_cfg.client.post.return_value.response = {"success": True}
    mock_cfg.solver.solve_captcha.return_value = "token-123"

    with patch.object(AccountChallenge, "_get_session", return_value=None):
        with patch.object(
            AccountChallenge, "_submit_challenge", return_value=None
        ) as sc:
            with patch.object(
                AccountChallenge, "_complete_challenge", return_value=None
            ) as cc:
                challenge.defeat_challenge()
                sc.assert_called_once()
                cc.assert_called_once()
    log_message("Account challenge defeated successfully.")


def test_submit_challenge_failure(mock_cfg: MagicMock) -> None:
    raw_response = {"session_id": "sess123"}
    challenge = AccountChallenge(mock_cfg.client, raw_response, mock_cfg)
    challenge.challenge_url = "https://challenge.spotify.com/c/sess123/chal456/"
    mock_cfg.client.post.return_value.fail = True
    with pytest.raises(GeneratorError):
        challenge._submit_challenge("token")
    log_message("_submit_challenge failure raised GeneratorError as expected.")


def test_complete_challenge_failure(mock_cfg: MagicMock) -> None:
    raw_response = {"session_id": "sess123"}
    challenge = AccountChallenge(mock_cfg.client, raw_response, mock_cfg)
    mock_cfg.client.post.return_value.fail = True
    with pytest.raises(GeneratorError):
        challenge._complete_challenge()
    log_message("_complete_challenge failure raised GeneratorError as expected.")


def test_register_save_error_logs(mock_cfg: MagicMock) -> None:
    creator: Creator = Creator(mock_cfg)
    mock_cfg.client.get.return_value.fail = False
    mock_cfg.client.get.return_value.response = (
        '{"signupServiceAppKey":"key","spT":"inst","csrfToken":"csrf","flowId":"flow"}'
    )
    mock_cfg.solver.solve_captcha.return_value = "token123"
    mock_cfg.client.post.return_value.fail = False
    mock_cfg.client.post.return_value.response = {"success": True}
    mock_cfg.saver.save.side_effect = Exception("save failed")

    creator.register()

    mock_cfg.logger.error.assert_called()
    log_message("Register save error triggered logger.error as expected.")

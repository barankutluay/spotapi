from unittest.mock import MagicMock, patch

import pytest

from creator import AccountChallenge, Creator, GeneratorError
from spotapi_tests.helpers import log_message, log_table


# --------------------------------------------------------------------------------------
# Unit Tests: Creator
# --------------------------------------------------------------------------------------
def test_creator_initialization_defaults(mock_cfg: MagicMock) -> None:
    creator = Creator(mock_cfg)
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
    creator = Creator(mock_cfg)
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
    creator = Creator(mock_cfg)
    with pytest.raises(GeneratorError):
        creator._get_session()
    log_message("Session retrieval failed as expected.")


def test_build_payload_structure(mock_cfg: MagicMock) -> None:
    creator = Creator(mock_cfg)
    creator.api_key, creator.installation_id, creator.flow_id = "k", "i", "f"
    payload = creator._build_payload("captcha-token")
    log_table("Payload Keys", {k: type(v).__name__ for k, v in payload.items()})
    assert payload["recaptcha_token"] == "captcha-token"
    assert payload["client_info"]["api_key"] == "k"


def test_process_register_handles_challenge(mock_cfg: MagicMock) -> None:
    creator = Creator(mock_cfg)
    creator.api_key, creator.installation_id, creator.flow_id = "a", "b", "c"
    mock_cfg.client.post.return_value.fail = False
    mock_cfg.client.post.return_value.response = {"challenge": True}
    with patch("creator.AccountChallenge") as MockChallenge:
        creator._process_register("captcha123")
        MockChallenge.assert_called_once()
    log_message("Challenge handled successfully.")


def test_process_register_success(mock_cfg: MagicMock) -> None:
    creator = Creator(mock_cfg)
    creator.api_key, creator.installation_id, creator.flow_id = "a", "b", "c"
    mock_cfg.client.post.return_value.fail = False
    mock_cfg.client.post.return_value.response = {"success": True}
    try:
        creator._process_register("captcha456")
    except Exception:
        pytest.fail("_process_register raised an exception unexpectedly")
    log_message("_process_register success path executed.")


def test_post_request_success(mock_cfg: MagicMock) -> None:
    creator = Creator(mock_cfg)
    mock_cfg.client.post.return_value.fail = False
    mock_cfg.client.post.return_value.response = {"ok": True}
    resp = creator._post_request("url", {"foo": "bar"})
    assert resp == {"ok": True}
    log_message("_post_request success path executed.")


def test_post_request_failure(mock_cfg: MagicMock) -> None:
    creator = Creator(mock_cfg)
    mock_cfg.client.post.return_value.fail = True
    mock_cfg.client.post.return_value.error.string = "fail"
    with pytest.raises(GeneratorError):
        creator._post_request("url", {"payload": 1})
    log_message("_post_request failure raised GeneratorError as expected.")


def test_register_saver_branch_true(mock_cfg: MagicMock) -> None:
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

    mock_cfg.saver.save.assert_called_once()
    log_message("Creator.register() called saver.save() as expected (branch true).")


def test_register_saver_branch_false(mock_cfg: MagicMock) -> None:
    cfg_no_saver = MagicMock(
        client=mock_cfg.client,
        solver=mock_cfg.solver,
        saver=None,
        logger=mock_cfg.logger,
    )

    cfg_no_saver.client.get.return_value.fail = False
    cfg_no_saver.client.get.return_value.response = (
        '{"signupServiceAppKey":"key","spT":"inst","csrfToken":"csrf","flowId":"flow"}'
    )
    cfg_no_saver.solver.solve_captcha.return_value = "captcha-token"
    cfg_no_saver.client.post.return_value.fail = False
    cfg_no_saver.client.post.return_value.response = {"success": True}

    creator = Creator(cfg_no_saver)
    creator.register()

    log_message("Creator.register() skipped saver.save() as expected (branch false).")


def test_register_without_solver(mock_cfg: MagicMock) -> None:
    mock_cfg.solver = None
    mock_cfg.client.get.return_value.fail = False
    mock_cfg.client.get.return_value.response = (
        '{"signupServiceAppKey":"key","spT":"inst","csrfToken":"csrf","flowId":"flow"}'
    )
    creator = Creator(mock_cfg)
    with pytest.raises(GeneratorError) as exc:
        creator.register()
    assert "Solver not set" in str(exc.value)
    log_message(
        "Creator.register raised GeneratorError due to missing solver as expected."
    )


def test_register_full_flow(mock_cfg: MagicMock) -> None:
    creator = Creator(mock_cfg)
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


def test_register_save_success_logs(mock_cfg: MagicMock) -> None:
    creator = Creator(mock_cfg)
    mock_cfg.client.get.return_value.fail = False
    mock_cfg.client.get.return_value.response = (
        '{"signupServiceAppKey":"key","spT":"inst","csrfToken":"csrf","flowId":"flow"}'
    )
    mock_cfg.solver.solve_captcha.return_value = "token123"
    mock_cfg.client.post.return_value.fail = False
    mock_cfg.client.post.return_value.response = {"success": True}
    mock_cfg.saver.save.return_value = None

    creator.register()
    mock_cfg.logger.info.assert_any_call(f"Account {creator.email} saved successfully.")
    log_message("Register save success triggered logger.info as expected.")


def test_register_save_error_logs(mock_cfg: MagicMock) -> None:
    creator = Creator(mock_cfg)
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


# --------------------------------------------------------------------------------------
# Unit Tests: AccountChallenge
# --------------------------------------------------------------------------------------
def test_account_challenge_get_session_success(mock_cfg: MagicMock) -> None:
    raw_response = {"session_id": "sess123"}
    challenge = AccountChallenge(mock_cfg.client, raw_response, mock_cfg)
    mock_cfg.client.post.return_value.fail = False
    mock_cfg.client.post.return_value.response = {
        "url": "https://challenge.spotify.com/c/sess123/chal456/"
    }
    challenge._get_session()
    assert challenge.challenge_url == "https://challenge.spotify.com/c/sess123/chal456/"
    log_message("AccountChallenge._get_session success executed.")


def test_account_challenge_get_session_failure(mock_cfg: MagicMock) -> None:
    raw_response = {"session_id": "sess123"}
    challenge = AccountChallenge(mock_cfg.client, raw_response, mock_cfg)
    mock_cfg.client.post.return_value.fail = True
    mock_cfg.client.post.return_value.error.string = "session fail"
    with pytest.raises(GeneratorError) as exc:
        challenge._get_session()
    assert "Could not get challenge session" in str(exc.value)
    log_message("_get_session failure raised GeneratorError as expected.")


def test_submit_challenge_failure(mock_cfg: MagicMock) -> None:
    raw_response = {"session_id": "sess123"}
    challenge = AccountChallenge(mock_cfg.client, raw_response, mock_cfg)
    challenge.challenge_url = "https://challenge.spotify.com/c/sess123/chal456/"
    mock_cfg.client.post.return_value.fail = True
    with pytest.raises(GeneratorError):
        challenge._submit_challenge("token")
    log_message("_submit_challenge failure raised GeneratorError as expected.")


def test_submit_challenge_success_path(mock_cfg: MagicMock) -> None:
    raw_response = {"session_id": "sess123"}
    challenge = AccountChallenge(mock_cfg.client, raw_response, mock_cfg)
    challenge.challenge_url = "https://challenge.spotify.com/c/sess123/chal456/"

    mock_cfg.client.post.return_value.fail = False
    mock_cfg.client.post.return_value.response = {"success": True}

    try:
        challenge._submit_challenge("token123")
    except Exception:
        pytest.fail("_submit_challenge raised an exception unexpectedly")

    log_message("_submit_challenge success path executed without exception.")


def test_complete_challenge_failure(mock_cfg: MagicMock) -> None:
    raw_response = {"session_id": "sess123"}
    challenge = AccountChallenge(mock_cfg.client, raw_response, mock_cfg)
    mock_cfg.client.post.return_value.fail = True
    with pytest.raises(GeneratorError):
        challenge._complete_challenge()
    log_message("_complete_challenge failure raised GeneratorError as expected.")


def test_account_challenge_complete_challenge_failure_response(
    mock_cfg: MagicMock,
) -> None:
    raw_response = {"session_id": "sess123"}
    challenge = AccountChallenge(mock_cfg.client, raw_response, mock_cfg)
    mock_cfg.client.post.return_value.fail = False
    mock_cfg.client.post.return_value.response = {"fail": True}
    with pytest.raises(GeneratorError) as exc:
        challenge._complete_challenge()
    assert "Could not complete challenge" in str(exc.value)
    log_message("_complete_challenge failure path raised GeneratorError as expected.")


def test_defeat_challenge_without_solver_raises(mock_cfg: MagicMock) -> None:
    raw_response = {"session_id": "sess123"}
    challenge = AccountChallenge(mock_cfg.client, raw_response, mock_cfg)
    mock_cfg.solver = None
    with patch.object(AccountChallenge, "_get_session", return_value=None):
        with pytest.raises(GeneratorError) as exc:
            challenge.defeat_challenge()
        assert "Solver not set" in str(exc.value)
    log_message(
        "AccountChallenge.defeat_challenge raised GeneratorError due to missing solver as expected."
    )


def test_account_challenge_flow(mock_cfg: MagicMock) -> None:
    raw_response = {"session_id": "sess123"}
    challenge = AccountChallenge(mock_cfg.client, raw_response, mock_cfg)
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


def test_account_challenge_complete_challenge_success(mock_cfg: MagicMock) -> None:
    raw_response = {"session_id": "sess123"}
    challenge = AccountChallenge(mock_cfg.client, raw_response, mock_cfg)
    mock_cfg.client.post.return_value.fail = False
    mock_cfg.client.post.return_value.response = {"success": True}
    try:
        challenge._complete_challenge()
    except Exception:
        pytest.fail("_complete_challenge raised an exception unexpectedly")
    log_message("_complete_challenge executed successfully without exceptions.")

import time
from unittest.mock import MagicMock

import pytest

from client import (
    _FALLBACK_SECRET,
    BaseClient,
    BaseClientError,
    _Undefined,
    generate_totp,
    get_latest_totp_secret,
)
from spotapi_tests.helpers import log_table


# --------------------------------------------------------------------------------------
# Unit Tests
# --------------------------------------------------------------------------------------
def test_totp_generation_fallback(monkeypatch):
    monkeypatch.setattr(
        "client.requests.get", lambda *a, **k: (_ for _ in ()).throw(Exception("fail"))
    )
    version, secret = _FALLBACK_SECRET
    totp, ver = generate_totp()
    log_table("TOTP Fallback", {"Version": ver, "TOTP": totp})
    assert ver == version
    assert isinstance(totp, str)


def test_get_latest_totp_secret_success(monkeypatch):
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {"18": [1, 2, 3]}
    monkeypatch.setattr("client.requests.get", lambda url, timeout: mock_resp)
    version, secret = get_latest_totp_secret()
    log_table("TOTP Secret Fetch", {"Version": version, "Secret Bytes": list(secret)})
    assert isinstance(secret, bytearray)


def test_get_latest_totp_secret_cache(monkeypatch):
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {"18": [1, 2, 3]}
    monkeypatch.setattr("client.requests.get", lambda url, timeout: mock_resp)
    v1, s1 = get_latest_totp_secret()
    v2, s2 = get_latest_totp_secret()
    assert v1 == v2
    assert list(s1) == list(s2)


def test_get_latest_totp_secret_cache_expiry(monkeypatch):
    import client as mod

    mod._secret_cache = (18, bytearray([1, 2, 3]))
    mod._cache_expiry = time.time() - 1

    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {"19": [4, 5, 6]}
    monkeypatch.setattr("client.requests.get", lambda url, timeout: mock_resp)

    version, secret = mod.get_latest_totp_secret()
    assert version == "19"
    assert list(secret) == [4, 5, 6]


def test_generate_totp_returns_valid_string(monkeypatch):
    monkeypatch.setattr(
        "client.get_latest_totp_secret", lambda: (18, bytearray([1, 2, 3]))
    )
    totp, version = generate_totp()
    assert totp.isdigit() or len(totp) > 0
    assert version == 18


def test_baseclient_initialization(mock_cfg: MagicMock):
    client = BaseClient(mock_cfg.client)
    assert client.client == mock_cfg.client
    assert callable(client.client.authenticate)


def test_auth_rule_with_existing_tokens(mock_cfg: MagicMock):
    client = BaseClient(mock_cfg.client)
    client.client_token = "token"
    client.access_token = "access"
    kwargs = {}
    result = client._auth_rule(kwargs)
    assert "Authorization" in result["headers"]
    assert result["headers"]["Client-Token"] == "token"


def test_auth_rule_with_existing_headers(mock_cfg: MagicMock):
    client = BaseClient(mock_cfg.client)
    client.client_token = "token"
    client.access_token = "access"
    kwargs = {"headers": {"Existing": "header"}}
    res = client._auth_rule(kwargs)
    assert "Existing" in res["headers"]
    assert res["headers"]["Client-Token"] == "token"


def test_auth_rule_missing_headers_branch(mock_cfg: MagicMock):
    client = BaseClient(mock_cfg.client)
    client.get_client_token = MagicMock()
    client.get_session = MagicMock()
    kwargs = {}
    res = client._auth_rule(kwargs)
    assert "headers" in res


def test__get_auth_vars_raises_on_fail(mock_cfg: MagicMock, monkeypatch):
    client = BaseClient(mock_cfg.client)
    client.access_token = _Undefined
    client.client_id = _Undefined

    resp = MagicMock()
    resp.fail = True
    resp.error.string = "fail"
    mock_cfg.client.get.return_value = resp

    monkeypatch.setattr("client.generate_totp", lambda: ("123", 18))

    with pytest.raises(BaseClientError):
        client._get_auth_vars()


def test_get_session_success(mock_cfg: MagicMock):
    client = BaseClient(mock_cfg.client)
    resp = MagicMock()
    resp.fail = False
    resp.response = (
        '<script src="https://open.spotifycdn.com/cdn/build/web-player/web-player.123.js"></script>'
        '<script src="https://open.spotifycdn.com/cdn/build/web-player/web-player.456.js"></script>'
    )
    mock_cfg.client.get.return_value = resp
    client._get_auth_vars = MagicMock()
    client.client.cookies.get = MagicMock(return_value="device123")
    client.get_session()
    assert client.js_pack.startswith("https://open.spotifycdn.com")


def test_get_session_indexerror_branch(mock_cfg: MagicMock):
    client = BaseClient(mock_cfg.client)
    resp = MagicMock()
    resp.fail = False
    resp.response = '<script src="https://open.spotifycdn.com/cdn/build/web-player/web-player.123.js"></script>'
    mock_cfg.client.get.return_value = resp
    client._get_auth_vars = MagicMock()
    client.client.cookies.get = MagicMock(return_value="device123")
    with pytest.raises(IndexError):
        client.get_session()


def test_get_session_second_pattern_branch(mock_cfg: MagicMock):
    client = BaseClient(mock_cfg.client)
    resp = MagicMock()
    resp.fail = False
    resp.response = (
        '<script src="https://open-exp.spotifycdn.com/cdn/build/web-player/web-player.123.js"></script>'
        '<script src="https://open-exp.spotifycdn.com/cdn/build/web-player/web-player.456.js"></script>'
    )
    mock_cfg.client.get.return_value = resp
    client._get_auth_vars = MagicMock()
    client.client.cookies.get = MagicMock(return_value="device123")
    client.get_session()
    assert client.js_pack.startswith("https://open-exp.spotifycdn.com")


def test_get_session_failure(mock_cfg: MagicMock):
    client = BaseClient(mock_cfg.client)
    resp = MagicMock()
    resp.fail = True
    resp.error.string = "fail"
    mock_cfg.client.get.return_value = resp
    with pytest.raises(BaseClientError):
        client.get_session()


def test_get_client_token_success(mock_cfg: MagicMock):
    client = BaseClient(mock_cfg.client)
    client.client_id = "id"
    client.device_id = "device"
    client.client_version = "v1"
    resp = MagicMock()
    resp.fail = False
    resp.response = {
        "response_type": "RESPONSE_GRANTED_TOKEN_RESPONSE",
        "granted_token": {"token": "abc"},
    }
    mock_cfg.client.post.return_value = resp
    client.get_client_token()
    assert client.client_token == "abc"


def test_get_client_token_different_response_type(mock_cfg: MagicMock):
    client = BaseClient(mock_cfg.client)
    client.client_id = "id"
    client.device_id = "device"
    client.client_version = "v1"
    client.get_session = MagicMock()
    client.get_sha256_hash = MagicMock()
    resp = MagicMock()
    resp.fail = False
    resp.response = {"response_type": "OTHER_TYPE"}
    mock_cfg.client.post.return_value = resp
    with pytest.raises(BaseClientError):
        client.get_client_token()


def test_get_client_token_failure(mock_cfg: MagicMock):
    client = BaseClient(mock_cfg.client)
    client.client_id = "id"
    client.device_id = "device"
    client.client_version = "v1"
    resp = MagicMock()
    resp.fail = True
    resp.error.string = "fail"
    mock_cfg.client.post.return_value = resp
    with pytest.raises(BaseClientError):
        client.get_client_token()


def test_get_client_token_invalid_json(mock_cfg: MagicMock):
    client = BaseClient(mock_cfg.client)
    client.client_id = "id"
    client.device_id = "device"
    client.client_version = "v1"
    resp = MagicMock()
    resp.fail = False
    resp.response = {}
    mock_cfg.client.post.return_value = resp
    with pytest.raises(BaseClientError):
        client.get_client_token()


def test_part_hash_requires_js_pack(mock_cfg: MagicMock):
    client = BaseClient(mock_cfg.client)
    client.js_pack = "url"
    client.get_session = MagicMock()
    client.raw_hashes = '..."hashname","query","hashvalue"...'
    assert client.part_hash("hashname") == "hashvalue"

    client.raw_hashes = '..."hashname","mutation","hashvalue2"...'
    assert client.part_hash("hashname") == "hashvalue2"


def test_part_hash_raises_value_error(mock_cfg: MagicMock):
    client = BaseClient(mock_cfg.client)
    client.raw_hashes = _Undefined
    client.get_sha256_hash = MagicMock()
    with pytest.raises(ValueError):
        client.part_hash("hashname")


def test_get_sha256_hash_no_js_pack_raises(mock_cfg: MagicMock):
    client = BaseClient(mock_cfg.client)
    client.js_pack = _Undefined
    client.get_session = MagicMock()
    with pytest.raises(ValueError):
        client.get_sha256_hash()


def test_get_sha256_hash_fail_branch(mock_cfg: MagicMock):
    client = BaseClient(mock_cfg.client)
    client.js_pack = "url"
    resp_fail = MagicMock()
    resp_fail.fail = True
    resp_fail.error.string = "fail"
    mock_cfg.client.get.return_value = resp_fail
    with pytest.raises(BaseClientError):
        client.get_sha256_hash()


def test_get_sha256_hash_success(mock_cfg: MagicMock):
    client = BaseClient(mock_cfg.client)
    client.js_pack = "url"

    resp_success = MagicMock()
    resp_success.fail = False
    resp_success.response = (
        'clientVersion:"v123",123:"xpui-routes-search",456:"xpui-routes-track-v2"'
    )

    mock_cfg.client.get.side_effect = [resp_success, resp_success, resp_success]

    client.get_sha256_hash()

    expected_raw = resp_success.response * 3
    assert client.raw_hashes == expected_raw
    assert client.client_version == "v123"
    assert client.xpui_route == "xpui-routes-search"
    assert client.xpui_route_tracks == "xpui-routes-track-v2"


def test_baseclient_str(mock_cfg: MagicMock):
    client = BaseClient(mock_cfg.client)
    s = str(client)
    assert s.startswith("BaseClient")


def test_get_latest_totp_secret_fail_status(monkeypatch):
    mock_resp = MagicMock()
    mock_resp.ok = False
    mock_resp.status_code = 500
    monkeypatch.setattr("client.requests.get", lambda url, timeout: mock_resp)
    import client as mod

    mod._secret_cache = None
    mod._cache_expiry = -1

    version, secret = mod.get_latest_totp_secret()
    assert (version, secret) == mod._FALLBACK_SECRET


def test_get_latest_totp_secret_invalid_list(monkeypatch):
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {"18": "not a list"}
    monkeypatch.setattr("client.requests.get", lambda url, timeout: mock_resp)
    import client as mod

    mod._secret_cache = None
    mod._cache_expiry = -1

    version, secret = mod.get_latest_totp_secret()
    assert (version, secret) == mod._FALLBACK_SECRET


def test__get_auth_vars_with_undefined_tokens(mock_cfg: MagicMock, monkeypatch):
    client = BaseClient(mock_cfg.client)
    client.access_token = _Undefined
    client.client_id = _Undefined

    resp = MagicMock()
    resp.fail = False
    resp.response = {"accessToken": "tok", "clientId": "id"}
    mock_cfg.client.get.return_value = resp

    monkeypatch.setattr("client.generate_totp", lambda: ("123", 18))

    client._get_auth_vars()
    assert client.access_token == "tok"
    assert client.client_id == "id"


def test__get_auth_vars_noop_when_defined(mock_cfg: MagicMock):
    client = BaseClient(mock_cfg.client)
    client.access_token = "already"
    client.client_id = "already-id"

    mock_cfg.client.get.side_effect = Exception("client.get should not be called")
    client._get_auth_vars()

    assert client.access_token == "already"
    assert client.client_id == "already-id"


def test_get_client_token_calls_get_session_when_missing_ids(mock_cfg: MagicMock):
    client = BaseClient(mock_cfg.client)
    client.client_id = None
    client.device_id = None
    client.client_version = "vX"

    called = {"called": False}

    def fake_get_session():
        called["called"] = True
        client.client_id = "id_from_session"
        client.device_id = "device_from_session"

    client.get_session = fake_get_session

    resp_post = MagicMock()
    resp_post.fail = False
    resp_post.response = {
        "response_type": "RESPONSE_GRANTED_TOKEN_RESPONSE",
        "granted_token": {"token": "tok123"},
    }
    mock_cfg.client.post.return_value = resp_post

    client.get_client_token()

    assert called["called"] is True
    assert client.client_token == "tok123"


def test_get_client_token_triggers_get_sha256_hash(mock_cfg: MagicMock):
    client = BaseClient(mock_cfg.client)
    client.client_id = "id"
    client.device_id = "device"
    client.client_version = None

    called = {"called": False}

    def fake_get_sha256_hash():
        called["called"] = True
        client.raw_hashes = (
            'clientVersion:"vX",1:"xpui-routes-search",2:"xpui-routes-track-v2"'
        )
        client.client_version = "vX"

    client.get_sha256_hash = fake_get_sha256_hash

    resp_post = MagicMock()
    resp_post.fail = False
    resp_post.response = {
        "response_type": "RESPONSE_GRANTED_TOKEN_RESPONSE",
        "granted_token": {"token": "abc"},
    }
    mock_cfg.client.post.return_value = resp_post

    client.get_client_token()
    assert called["called"] is True
    assert client.client_token == "abc"


def test_get_client_token_invalid_json_branch(mock_cfg: MagicMock):
    client = BaseClient(mock_cfg.client)
    client.client_id = "id"
    client.device_id = "device"
    client.client_version = "v1"

    fake_response = MagicMock()
    fake_response.get.return_value = "RESPONSE_GRANTED_TOKEN_RESPONSE"
    resp = MagicMock()
    resp.fail = False
    resp.response = fake_response

    mock_cfg.client.post.return_value = resp

    with pytest.raises(BaseClientError) as excinfo:
        client.get_client_token()
    assert "Invalid JSON" in str(excinfo.value)


def test_get_sha256_hash_fail_xpui(monkeypatch, mock_cfg: MagicMock):
    client = BaseClient(mock_cfg.client)
    client.js_pack = "url"
    resp_fail = MagicMock()
    resp_fail.fail = True
    resp_fail.error.string = "fail"
    mock_cfg.client.get.return_value = resp_fail
    with pytest.raises(BaseClientError):
        client.get_sha256_hash()


def test_get_sha256_hash_xpui_fail(mock_cfg: MagicMock):
    client = BaseClient(mock_cfg.client)
    client.js_pack = "some_url"

    resp_main = MagicMock()
    resp_main.fail = False
    resp_main.response = (
        'clientVersion:"vX",'
        '123:"xpui-routes-search",'
        '456:"xpui-routes-track-v2",'
        '123:"route_name",'
        '456:"track_route_name"'
    )

    resp_xpui_fail = MagicMock()
    resp_xpui_fail.fail = True
    resp_xpui_fail.error = MagicMock(string="xpui failed")
    mock_cfg.client.get.side_effect = [resp_main, resp_xpui_fail]

    with pytest.raises(BaseClientError) as exc:
        client.get_sha256_hash()

    assert "Could not get xpui hashes" in str(exc.value)

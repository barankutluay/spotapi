import uuid
from types import SimpleNamespace
from typing import Mapping
from unittest.mock import MagicMock

import pytest

from family import Family, FamilyError, JoinFamily
from spotapi_tests.helpers import log_message, log_table


# --------------------------------------------------------------------------------------
# Unit Tests: JoinFamily
# --------------------------------------------------------------------------------------
def test_join_init_sets_properties(mock_login, mock_host):
    j = JoinFamily(mock_login, mock_host, "US")
    log_table(
        "JoinFamily Init",
        {
            "address": j.address,
            "invite_token": j.invite_token,
            "session_id": j.session_id,
        },
    )
    assert j.address == "123 Fake St"
    assert j.invite_token == "invite_abc123"
    assert isinstance(uuid.UUID(j.session_id), uuid.UUID.__class__) or isinstance(
        j.session_id, str
    )


def test__get_session_success(mock_login, mock_host):
    j = JoinFamily(mock_login, mock_host, "US")

    mock_resp = SimpleNamespace(
        fail=False, response='{"csrfToken":"csrf_val"}', raw=None
    )
    j.client.get.return_value = mock_resp

    j._get_session()
    log_table("Get Session", {"csrf": j.csrf})
    assert j.csrf == "csrf_val"


def test__get_session_fail_raises(mock_login, mock_host):
    j = JoinFamily(mock_login, mock_host, "US")
    mock_resp = SimpleNamespace(
        fail=True, status_code=500, error=SimpleNamespace(string="err")
    )
    j.client.get.return_value = mock_resp

    with pytest.raises(FamilyError) as exc:
        j._get_session()
    log_message("Get session failed as expected.")
    assert "Could not get session" in str(exc.value)


def test__get_autocomplete_success_updates_addresses_and_csrf(mock_login, mock_host):
    j = JoinFamily(mock_login, mock_host, "US")
    j.csrf = "old"
    payload_addresses = [
        {"address": {"googlePlaceId": "g1"}, "other": "x"},
        {"address": {"googlePlaceId": "g2"}},
    ]
    mock_resp = SimpleNamespace(
        fail=False,
        response={"addresses": payload_addresses},
        raw=SimpleNamespace(headers={"X-Csrf-Token": "new_csrf"}),
    )
    j.client.post.return_value = mock_resp

    j._get_autocomplete("some address")
    log_table(
        "Autocomplete Result", {"addresses_count": len(j.addresses), "csrf": j.csrf}
    )
    assert j.addresses == payload_addresses
    assert j.csrf == "new_csrf"


def test__get_autocomplete_fail_raises(mock_login, mock_host):
    j = JoinFamily(mock_login, mock_host, "US")
    j.csrf = "old"
    mock_resp = SimpleNamespace(
        fail=True, status_code=400, error=SimpleNamespace(string="err")
    )
    j.client.post.return_value = mock_resp

    with pytest.raises(FamilyError) as exc:
        j._get_autocomplete("addr")
    log_message("Autocomplete failed as expected.")
    assert "Could not get address autocomplete" in str(exc.value)


def test__try_address_returns_true_on_success_and_updates_csrf(mock_login, mock_host):
    j = JoinFamily(mock_login, mock_host, "US")
    j.csrf = "csrf_old"
    candidate = {"address": {"googlePlaceId": "place_1"}}
    mock_resp = SimpleNamespace(
        fail=False, raw=SimpleNamespace(headers={"X-Csrf-Token": "csrf_upd"})
    )
    j.client.post.return_value = mock_resp

    ok = j._try_address(candidate)
    log_table("Try Address Success", {"ok": ok, "csrf": j.csrf})
    assert ok is True
    assert j.csrf == "csrf_upd"


def test__try_address_returns_false_on_fail_and_updates_csrf(mock_login, mock_host):
    j = JoinFamily(mock_login, mock_host, "US")
    j.csrf = "csrf_old"
    candidate = {"address": {"googlePlaceId": "place_1"}}
    mock_resp = SimpleNamespace(
        fail=True, raw=SimpleNamespace(headers={"X-Csrf-Token": "csrf_upd"})
    )
    j.client.post.return_value = mock_resp

    ok = j._try_address(candidate)
    log_table("Try Address Fail", {"ok": ok, "csrf": j.csrf})
    assert ok is False
    assert j.csrf == "csrf_upd"


def test__get_address_confirms_first_valid_candidate(
    monkeypatch, mock_login, mock_host
):
    j = JoinFamily(mock_login, mock_host, "US")

    def fake_get_session(self):
        self.csrf = "csrf1"

    addresses = [
        {"address": {"googlePlaceId": "g_a"}},
        {"address": {"googlePlaceId": "g_b"}},
    ]

    def fake_get_autocomplete(self, addr):
        self.addresses = addresses

    calls = {"i": 0}

    def try_addr(self, a):
        calls["i"] += 1
        return calls["i"] == 2

    monkeypatch.setattr(JoinFamily, "_get_session", fake_get_session, raising=True)
    monkeypatch.setattr(
        JoinFamily, "_get_autocomplete", fake_get_autocomplete, raising=True
    )
    monkeypatch.setattr(JoinFamily, "_try_address", try_addr, raising=True)

    pid = j._get_address()
    log_table("Get Address", {"selected_place_id": pid})
    assert pid == "g_b"


def test__get_address_raises_when_no_candidate_confirmed(
    monkeypatch, mock_login, mock_host
):
    j = JoinFamily(mock_login, mock_host, "US")

    def fake_get_session(self):
        self.csrf = "csrf1"

    def fake_get_autocomplete(self, addr):
        self.addresses = [{"address": {"googlePlaceId": "g1"}}]

    def always_false_try(self, a):
        return False

    monkeypatch.setattr(JoinFamily, "_get_session", fake_get_session, raising=True)
    monkeypatch.setattr(
        JoinFamily, "_get_autocomplete", fake_get_autocomplete, raising=True
    )
    monkeypatch.setattr(JoinFamily, "_try_address", always_false_try, raising=True)

    with pytest.raises(FamilyError):
        j._get_address()
    log_message("No candidate could be confirmed; raised FamilyError as expected.")


def test__add_to_family_success_calls_post(mock_login, mock_host):
    j = JoinFamily(mock_login, mock_host, "US")
    j.csrf = "csrf_tok"
    mock_resp = SimpleNamespace(fail=False)
    j.client.post.return_value = mock_resp

    j._add_to_family("place_123")
    j.client.post.assert_called_once()
    called_url = j.client.post.call_args[0][0]
    log_table("Add To Family Call", {"url_called": called_url})
    assert called_url == j.ADD_FAMILY_URL


def test__add_to_family_fail_raises(mock_login, mock_host):
    j = JoinFamily(mock_login, mock_host, "US")
    j.csrf = "csrf_tok"
    mock_resp = SimpleNamespace(
        fail=True, status_code=403, error=SimpleNamespace(string="err")
    )
    j.client.post.return_value = mock_resp

    with pytest.raises(FamilyError) as exc:
        j._add_to_family("place_123")
    log_message("Add to family failed as expected.")
    assert "Could not add user to family" in str(exc.value)


def test_add_to_family_full_flow(monkeypatch, mock_login, mock_host):
    j = JoinFamily(mock_login, mock_host, "US")

    monkeypatch.setattr(
        JoinFamily, "_get_address", lambda self: "place_ok", raising=True
    )

    called = {"add": False}

    def fake_add(self, pid):
        called["add"] = True
        assert pid == "place_ok"

    monkeypatch.setattr(JoinFamily, "_add_to_family", fake_add, raising=True)

    j.add_to_family()
    log_message("add_to_family full flow executed.")
    assert called["add"] is True


# --------------------------------------------------------------------------------------
# Unit Tests: Family
# --------------------------------------------------------------------------------------
class DummyFamily(Family):
    """Family.__init__'i çalıştırmadan kullanmak için küçük stub."""

    def __init__(self):
        # intentionally don't call super().__init__
        self.login = MagicMock()
        self._user_family = None


def test_get_family_home_success():
    f = DummyFamily()
    f.login.client.get.return_value = SimpleNamespace(
        fail=False, response={"members": [{"id": 1}]}
    )
    out = Family.get_family_home(f)
    log_table("Family Home", {"members_count": len(out.get("members", []))})
    assert isinstance(out, Mapping)
    assert "members" in out


def test_get_family_home_fail_raises():
    f = DummyFamily()
    f.login.client.get.return_value = SimpleNamespace(
        fail=True, status_code=500, error=SimpleNamespace(string="err")
    )
    with pytest.raises(FamilyError):
        Family.get_family_home(f)
    log_message("get_family_home failure raised FamilyError as expected.")


def test_get_family_home_invalid_json_raises():
    f = DummyFamily()
    f.login.client.get.return_value = SimpleNamespace(
        fail=False, response="not_a_mapping"
    )
    with pytest.raises(FamilyError):
        Family.get_family_home(f)
    log_message("get_family_home invalid json raised FamilyError as expected.")


def test_members_property_caches_and_returns_list(monkeypatch):
    f = DummyFamily()
    called = {"count": 0}

    def gf():
        called["count"] += 1
        return {"members": [1, 2, 3]}

    monkeypatch.setattr(f, "get_family_home", gf)
    m1 = f.members
    m2 = f.members
    log_table("Members Cache", {"first": m1, "second": m2})
    assert m1 == [1, 2, 3]
    assert m2 == [1, 2, 3]
    assert called["count"] == 1


def test_enough_space_true_and_false():
    f = DummyFamily()
    f._user_family = {"members": [1, 2, 3]}
    log_table("Enough Space - Case 1", {"members": len(f._user_family["members"])})
    assert f.enough_space is True

    f._user_family = {"members": [1, 2, 3, 4, 5, 6]}
    log_table("Enough Space - Case 2", {"members": len(f._user_family["members"])})
    assert f.enough_space is False


def test_family_init_raises_if_not_premium(monkeypatch):
    import family as family_mod

    monkeypatch.setattr(
        family_mod.User, "has_premium", property(lambda self: False), raising=True
    )

    with pytest.raises(ValueError):
        Family(MagicMock())
    log_message("Family init raised ValueError for non-premium user as expected.")


def test_family_init_with_premium(monkeypatch):
    from unittest.mock import MagicMock

    import family as family_mod
    from family import Family

    monkeypatch.setattr(
        family_mod.User, "has_premium", property(lambda self: True), raising=True
    )

    f = Family(MagicMock())
    log_table("Family Init Premium", {"_user_family_is_none": f._user_family is None})
    assert f._user_family is None

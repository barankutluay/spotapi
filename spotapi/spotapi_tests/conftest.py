from typing import Generator
from unittest.mock import MagicMock

import pytest
from helpers import REPORT_PATH


@pytest.fixture
def mock_cfg() -> MagicMock:
    client = MagicMock()
    solver = MagicMock()
    saver = MagicMock()
    logger = MagicMock()
    cfg = MagicMock(client=client, solver=solver, saver=saver, logger=logger)
    return cfg


@pytest.fixture
def mock_login() -> MagicMock:
    client = MagicMock()
    login = MagicMock(client=client)
    return login


@pytest.fixture
def mock_host() -> MagicMock:
    host = MagicMock()
    host.get_family_home.return_value = {
        "address": "123 Fake St",
        "inviteToken": "invite_abc123",
    }
    return host


@pytest.fixture
def mock_client() -> Generator[MagicMock, None, None]:
    client = MagicMock()
    yield client


@pytest.fixture(scope="session", autouse=True)
def clear_report():
    if REPORT_PATH.exists():
        REPORT_PATH.unlink()
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    yield

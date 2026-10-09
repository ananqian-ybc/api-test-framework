"""TokenManager 集成测试：验证缓存、失效重登与错误信息。"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from common.exceptions import ApiTestError
from common.http_client import ApiClient
from common.token_manager import TokenManager
from mock_server.store import TEST_PASSWORD
from tests.support.player import new_account


def test_should_cache_token_and_login_only_once(
    token_manager_for: Callable[..., TokenManager]
) -> None:
    manager = token_manager_for(new_account("tm"))

    first = manager.get_token()
    second = manager.get_token()

    assert first == second
    assert manager.login_count == 1, "第二次取 Token 应命中缓存，不应再次登录"


def test_should_login_again_after_invalidate(token_manager_for: Callable[..., TokenManager]) -> None:
    manager = token_manager_for(new_account("tm"))
    first = manager.get_token()

    manager.invalidate()
    second = manager.get_token()

    assert second != first
    assert manager.login_count == 2


def test_should_raise_clear_error_when_credentials_invalid(
    token_manager_for: Callable[..., TokenManager]
) -> None:
    manager = token_manager_for(new_account("tm"), "wrong-password")

    with pytest.raises(ApiTestError) as error:
        manager.get_token()

    message = str(error.value)
    assert "登录失败" in message
    assert "401" in message
    assert manager.login_count == 0, "登录失败不应计数为成功登录"


def test_invalidate_should_be_idempotent(token_manager_for: Callable[..., TokenManager]) -> None:
    manager = token_manager_for(new_account("tm"))
    manager.get_token()

    manager.invalidate()
    manager.invalidate()

    assert manager.get_token()
    assert manager.login_count == 2


def test_should_login_with_configured_account(raw_client: ApiClient) -> None:
    """TokenManager 只认账号密码，与领域无关（游戏账号同样适用）。"""
    manager = TokenManager(raw_client, new_account("tm"), TEST_PASSWORD)

    assert len(manager.get_token()) == 32, "mock 服务端返回 32 位十六进制 Token"

"""ApiClient 集成测试：对真实游戏服务端发请求，验证封装行为是否符合契约。"""

from __future__ import annotations

import socket
from dataclasses import replace

import pytest
import requests

from common.exceptions import ApiConnectionError, ApiTimeoutError
from common.http_client import ApiClient, ApiResponse
from common.settings import Settings
from mock_server.store import TEST_PASSWORD
from tests.support.player import Player


def test_should_call_health_endpoint_without_token(settings: Settings) -> None:
    response = ApiClient(settings).get("/health", auth=False)

    assert response.status_code == 200
    assert response.json == {"status": "ok"}
    assert response.ok is True


def test_should_record_method_url_and_elapsed_time(player: Player) -> None:
    response = player.client.get("/api/bag")

    assert response.method == "GET"
    assert response.url.endswith("/api/bag")
    assert response.elapsed_ms > 0


def test_should_attach_bearer_token_when_auth_enabled(player: Player) -> None:
    response = player.client.get("/api/role")

    assert response.status_code == 200
    assert response.json["role_id"] == player.role_id


def test_should_get_401_when_auth_is_disabled(settings: Settings) -> None:
    response = ApiClient(settings).get("/api/bag", auth=False)

    assert response.status_code == 401
    assert response.json["code"] == "UNAUTHORIZED"
    assert response.ok is False


def test_should_relogin_and_retry_once_when_token_invalidated(
    player: Player, raw_client: ApiClient
) -> None:
    """AC5：服务端让 Token 失效后，客户端应自动重登并完成请求，用例仍通过。

    场景贴近线上：长回归跑到一半 Token 过期，若没有自动重登，会产生大批"假失败"。
    """
    stale_token = player.token_manager.get_token()
    logout = raw_client.request(
        "POST",
        "/api/logout",
        json_body={},
        headers={"Authorization": f"Bearer {stale_token}"},
        auth=False,
    )
    assert logout.status_code == 200, logout.describe()
    logins_before = player.token_manager.login_count

    response = player.client.get("/api/role")

    assert response.status_code == 200, response.describe()
    assert player.token_manager.login_count == logins_before + 1
    assert player.token_manager.get_token() != stale_token


def test_should_raise_clear_error_when_service_unreachable(settings: Settings) -> None:
    with socket.socket() as probe:  # 申请一个确定没有服务监听的端口
        probe.bind(("127.0.0.1", 0))
        closed_port = int(probe.getsockname()[1])
    unreachable = replace(settings, base_url=f"http://127.0.0.1:{closed_port}", timeout=2)

    with pytest.raises(ApiConnectionError, match="无法连接被测服务"):
        ApiClient(unreachable).get("/health", auth=False)


class _TimeoutSession:
    """边界替身：模拟"已连上但响应超时"，用于验证超时到领域异常的映射。"""

    def request(self, *args: object, **kwargs: object) -> object:
        raise requests.exceptions.ReadTimeout("read timed out")


def test_should_map_timeout_to_domain_error(settings: Settings) -> None:
    client = ApiClient(settings, session=_TimeoutSession())

    with pytest.raises(ApiTimeoutError, match="超时"):
        client.get("/api/role")


def test_should_expose_response_text_and_headers(settings: Settings) -> None:
    response = ApiClient(settings).post(
        "/api/login",
        json_body={"username": "header_probe", "password": TEST_PASSWORD},
        auth=False,
    )

    assert isinstance(response, ApiResponse)
    assert response.headers["Content-Type"].startswith("application/json")
    assert "token" in response.text

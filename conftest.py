"""全局 fixture：拉起游戏服务端 mock、组装客户端、提供独立玩家账号。

设计要点：
1. 被测服务由本 fixture 自行启动（随机空闲端口），用完即关，保证用例可重复运行；
2. 设置环境变量 API_TEST_BASE_URL 时改为对已有服务测试（CI / 演示环境）；
3. `player` 为每个用例创建独立账号 + 已创角，从根上消除用例之间的数据污染；
4. `raw_client` 为无鉴权客户端，用于登录接口本身与越权场景。
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from dataclasses import replace
from pathlib import Path

import pytest

from common.http_client import ApiClient
from common.settings import Settings, load_settings
from common.token_manager import TokenManager
from mock_server.store import TEST_PASSWORD
from tests.support.player import Player, build_player, new_account

PROJECT_ROOT = Path(__file__).resolve().parent
STARTUP_TIMEOUT_SECONDS = 15.0


def _free_port() -> int:
    """向系统申请一个空闲端口，避免与本机已有服务冲突。"""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_until_healthy(base_url: str, process: subprocess.Popen[bytes]) -> None:
    """轮询 /health 直到服务就绪；失败时给出可定位的错误，而不是让用例超时。"""
    import requests

    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stderr = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
            raise RuntimeError(f"游戏服务端 mock 启动失败（退出码 {process.returncode}）：\n{stderr}")
        try:
            if requests.get(f"{base_url}/health", timeout=1).status_code == 200:
                return
        except requests.RequestException:
            time.sleep(0.2)
    raise RuntimeError(f"游戏服务端 mock 在 {STARTUP_TIMEOUT_SECONDS}s 内未就绪: {base_url}/health")


@pytest.fixture(scope="session")
def sut_base_url() -> Iterator[str]:
    """返回被测服务地址：优先复用外部服务，否则本地拉起游戏服务端 mock。"""
    external = os.environ.get("API_TEST_BASE_URL")
    if external:
        yield external.rstrip("/")
        return

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    process = subprocess.Popen(
        [sys.executable, "-m", "mock_server.app", "--port", str(port)],
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        _wait_until_healthy(base_url, process)
        yield base_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


@pytest.fixture(scope="session")
def settings(sut_base_url: str) -> Settings:
    """会话级配置：环境取自 config.yaml，地址以实际启动的服务为准。"""
    return replace(load_settings("dev"), base_url=sut_base_url)


@pytest.fixture(scope="session")
def raw_client(settings: Settings) -> ApiClient:
    """不带鉴权的客户端：用于登录接口本身与越权场景。"""
    return ApiClient(settings)


@pytest.fixture
def player(settings: Settings, raw_client: ApiClient) -> Player:
    """独立玩家：全新账号 + 已创角，用例之间数据完全隔离。"""
    return build_player(settings, raw_client)


@pytest.fixture
def make_player(settings: Settings, raw_client: ApiClient):
    """需要多个玩家（多账号隔离用例）时使用。"""

    def _build(nickname: str = "自动化测试角色") -> Player:
        return build_player(settings, raw_client, nickname=nickname)

    return _build


@pytest.fixture
def account_client(settings: Settings, raw_client: ApiClient) -> Callable[[], ApiClient]:
    """返回「全新未创角账号」的已鉴权客户端工厂。

    创角类用例必须用未创角账号，且每次调用都换一个新账号，
    否则同一条数据驱动用例的多个参数会互相干扰（第一次创角成功后其余全变 409）。
    """

    def _build() -> ApiClient:
        return ApiClient(settings, auth=TokenManager(raw_client, new_account(), TEST_PASSWORD))

    return _build


@pytest.fixture
def unique_account():
    """生成唯一账号名，供登录/创角类用例使用。"""
    return new_account


@pytest.fixture(scope="session")
def test_password() -> str:
    return TEST_PASSWORD


@pytest.fixture
def token_manager_for(raw_client: ApiClient):
    """按账号构造 TokenManager，便于验证缓存与重登行为。"""

    def _build(account: str, password: str = TEST_PASSWORD) -> TokenManager:
        return TokenManager(raw_client, account, password)

    return _build

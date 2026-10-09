"""测试辅助：构造「独立玩家」上下文。

游戏用例最大的坑是**数据互相污染**：抽卡会扣钻石、领取邮件会改金币、
使用道具会改背包。如果所有用例共用一个账号，用例顺序一变结果就变。

因此约定：**每个用例一个全新账号 + 已创角**，账号之间数据完全隔离。
代价是每个用例多一次登录，换来的是用例可以任意顺序、任意并发执行。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from common.http_client import ApiClient
from common.settings import Settings
from common.token_manager import TokenManager
from mock_server.store import TEST_PASSWORD

DEFAULT_NICKNAME = "自动化测试角色"


@dataclass
class Player:
    """一个独立玩家的测试上下文。"""

    account: str
    client: ApiClient
    token_manager: TokenManager
    role: dict[str, Any]

    @property
    def role_id(self) -> int:
        return int(self.role["role_id"])

    def get_role(self) -> dict[str, Any]:
        """重新拉取角色数据，用于校验服务端持久化状态（而不是用本地猜测）。"""
        response = self.client.get("/api/role")
        assert response.status_code == 200, response.describe()
        return response.json

    def get_bag(self) -> dict[str, Any]:
        response = self.client.get("/api/bag")
        assert response.status_code == 200, response.describe()
        return response.json

    def get_mails(self) -> list[dict[str, Any]]:
        response = self.client.get("/api/mail")
        assert response.status_code == 200, response.describe()
        return response.json["mails"]


def new_account(prefix: str = "player") -> str:
    """生成唯一账号名，保证用例数据隔离。"""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def build_player(
    settings: Settings,
    raw_client: ApiClient,
    *,
    account: str | None = None,
    nickname: str = DEFAULT_NICKNAME,
) -> Player:
    """创建账号、登录并创角，返回可直接使用的玩家上下文。"""
    account_name = account or new_account()
    manager = TokenManager(raw_client, account_name, TEST_PASSWORD)
    client = ApiClient(settings, auth=manager)
    created = client.post("/api/role/create", json_body={"nickname": nickname})
    assert created.status_code == 201, created.describe()
    return Player(account=account_name, client=client, token_manager=manager, role=created.json)

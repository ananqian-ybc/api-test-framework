"""Token 管理：缓存 + 失效重登，避免每条用例都登录一次。

并发说明：pytest-xdist 为进程级隔离，每个 worker 进程各自持有一份 Token，
因此这里不需要加锁；这是"用进程隔离代替共享状态"的取舍。
"""

from __future__ import annotations

import logging

from common.exceptions import ApiBusinessError
from common.http_client import ApiClient

LOGIN_PATH = "/api/login"


class TokenManager:
    """Token 缓存与失效重登。"""

    def __init__(
        self,
        client: ApiClient,
        username: str,
        password: str,
        logger: logging.Logger | None = None,
        login_path: str = LOGIN_PATH,
    ) -> None:
        self._client = client
        self._username = username
        self._password = password
        self._logger = logger
        self._login_path = login_path
        self._token: str | None = None
        self._login_count = 0

    @property
    def login_count(self) -> int:
        """实际发生的登录次数，用于证明缓存生效。"""
        return self._login_count

    def get_token(self) -> str:
        """返回可用 Token：命中缓存直接返回，否则登录并缓存。"""
        if self._token is not None:
            return self._token

        response = self._client.post(
            self._login_path,
            json_body={"username": self._username, "password": self._password},
            auth=False,
        )
        if response.status_code != 200:
            raise ApiBusinessError(f"登录失败：状态码 {response.status_code}\n{response.describe()}")

        token = response.json.get("token")
        if not isinstance(token, str) or not token:
            raise ApiBusinessError(f"登录响应缺少 token 字段\n{response.describe()}")

        self._token = token
        self._login_count += 1
        if self._logger is not None:
            self._logger.info("登录成功（第 %d 次），Token 已缓存", self._login_count)
        return self._token

    def invalidate(self) -> None:
        """清空缓存，下次 get_token 会重新登录。"""
        self._token = None

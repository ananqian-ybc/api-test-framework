"""HTTP 客户端：统一鉴权、超时、耗时统计、日志与 401 自动重登。

为什么值得封装这三件事：
1. 鉴权集中在客户端 -> 用例里永远不出现 token 拼装，改鉴权方式只改一处；
2. 401 自动重登一次 -> 长回归中 Token 过期不再导致大批"假失败"（稳定性关键）；
3. 响应快照 ApiResponse -> 断言失败时能直接打印完整请求与响应。
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Protocol

import requests

from common.exceptions import ApiConnectionError, ApiTimeoutError
from common.logger import get_logger
from common.settings import Settings

ENCODING_PREVIEW_LIMIT = 200


@dataclass(frozen=True)
class ApiResponse:
    """一次请求的完整快照：断言失败时要靠它还原现场。"""

    method: str
    url: str
    status_code: int
    headers: dict[str, str]
    text: str
    elapsed_ms: float
    request_body: Any = None

    @property
    def ok(self) -> bool:
        """状态码是否落在 2xx。"""
        return 200 <= self.status_code < 300

    @property
    def json(self) -> Any:
        """解析后的响应体；非 JSON 时抛出可读的 ValueError。"""
        try:
            return json.loads(self.text)
        except json.JSONDecodeError as exc:
            preview = self.text[:ENCODING_PREVIEW_LIMIT]
            raise ValueError(f"响应体不是合法 JSON: {preview}") from exc

    def describe(self) -> str:
        """可读的完整请求/响应文本，用于断言失败信息与日志。"""
        request_body = (
            json.dumps(self.request_body, ensure_ascii=False)
            if self.request_body is not None
            else "-"
        )
        return (
            f"请求: {self.method} {self.url}\n"
            f"请求体: {request_body}\n"
            f"响应: {self.status_code} (耗时 {self.elapsed_ms:.1f}ms)\n"
            f"响应头: {self.headers}\n"
            f"响应体: {self.text}"
        )


class TokenProvider(Protocol):
    """ApiClient 依赖的最小鉴权接口，便于替换实现与测试。"""

    def get_token(self) -> str: ...

    def invalidate(self) -> None: ...


class ApiClient:
    """接口请求封装。"""

    def __init__(
        self,
        settings: Settings,
        auth: TokenProvider | None = None,
        session: requests.Session | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._settings = settings
        self._auth = auth
        self._session = session or requests.Session()
        self._logger = logger or get_logger()

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
        headers: dict[str, str] | None = None,
        auth: bool = True,
    ) -> ApiResponse:
        """发起请求；auth=True 且已配置 TokenProvider 时附加 Bearer 头。

        收到 401 时会清空本地 Token 并重登后重试一次——只重试一次，避免死循环。
        """
        request_headers = dict(headers or {})
        token: str | None = None
        if auth and self._auth is not None:
            token = self._auth.get_token()
            request_headers["Authorization"] = f"Bearer {token}"

        response = self._send(method, path, params, json_body, request_headers)

        if response.status_code == 401 and token is not None:
            self._logger.warning("Token 已失效，自动重登后重试一次: %s %s", method, path)
            self._auth.invalidate()
            request_headers["Authorization"] = f"Bearer {self._auth.get_token()}"
            response = self._send(method, path, params, json_body, request_headers)
        return response

    def get(self, path: str, **kwargs: Any) -> ApiResponse:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> ApiResponse:
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> ApiResponse:
        return self.request("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> ApiResponse:
        return self.request("DELETE", path, **kwargs)

    def _send(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None,
        json_body: Any,
        headers: dict[str, str],
    ) -> ApiResponse:
        url = f"{self._settings.base_url}{path}"
        started = time.perf_counter()
        try:
            raw = self._session.request(
                method=method,
                url=url,
                params=params,
                json=json_body,
                headers=headers,
                timeout=self._settings.timeout,
                verify=self._settings.verify_ssl,
            )
        except requests.ConnectTimeout as exc:
            raise ApiConnectionError(
                f"无法连接被测服务 {self._settings.base_url}，请确认它已启动: {exc}"
            ) from exc
        except requests.Timeout as exc:
            raise ApiTimeoutError(
                f"请求超时（{self._settings.timeout}s）: {method} {url}"
            ) from exc
        except requests.ConnectionError as exc:
            raise ApiConnectionError(
                f"无法连接被测服务 {self._settings.base_url}，请确认它已启动: {exc}"
            ) from exc

        response = ApiResponse(
            method=method,
            url=raw.url,
            status_code=raw.status_code,
            headers=dict(raw.headers),
            text=raw.text,
            elapsed_ms=(time.perf_counter() - started) * 1000,
            request_body=json_body,
        )
        self._logger.log(
            logging.INFO if response.ok else logging.WARNING,
            "%s %s -> %s (%.1fms)",
            response.method,
            response.url,
            response.status_code,
            response.elapsed_ms,
        )
        return response

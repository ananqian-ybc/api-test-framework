"""响应断言封装：断言失败必须能"还原现场"。

每个断言失败信息都附带完整请求与响应，让定位时间从"翻日志"降到"读报错"。
"""

from __future__ import annotations

from typing import Any

from common.http_client import ApiResponse

_MISSING = object()


def _json_body(response: ApiResponse) -> Any:
    try:
        return response.json
    except ValueError as exc:
        raise AssertionError(f"响应体不是合法 JSON，无法断言\n{response.describe()}") from exc


def _resolve_path(body: Any, path: str) -> Any:
    """按点号路径取值，支持列表下标，如 items.0.title。"""
    current = body
    for token in path.split("."):
        if isinstance(current, dict) and token in current:
            current = current[token]
        elif isinstance(current, list) and token.isdigit() and int(token) < len(current):
            current = current[int(token)]
        else:
            return _MISSING
    return current


def assert_status(response: ApiResponse, expected: int) -> None:
    """断言状态码。"""
    if response.status_code != expected:
        raise AssertionError(
            f"状态码不符：期望 {expected}，实际 {response.status_code}\n{response.describe()}"
        )


def assert_json_path(response: ApiResponse, path: str, expected: Any) -> None:
    """断言响应 JSON 中某个路径的值。"""
    body = _json_body(response)
    actual = _resolve_path(body, path)
    if actual is _MISSING:
        raise AssertionError(f"路径不存在：{path}\n{response.describe()}")
    if actual != expected:
        raise AssertionError(
            f"字段值不符：{path} 期望 {expected!r}，实际 {actual!r}\n{response.describe()}"
        )


def assert_json_contains(response: ApiResponse, subset: dict[str, Any]) -> None:
    """断言响应 JSON 至少包含 subset 中的键值对，用于多字段联合校验。"""
    body = _json_body(response)
    if not isinstance(body, dict):
        raise AssertionError(f"响应体不是 JSON 对象\n{response.describe()}")
    for key, expected in subset.items():
        if key not in body:
            raise AssertionError(f"响应体缺少字段：{key}\n{response.describe()}")
        if body[key] != expected:
            raise AssertionError(
                f"字段值不符：{key} 期望 {expected!r}，实际 {body[key]!r}\n{response.describe()}"
            )

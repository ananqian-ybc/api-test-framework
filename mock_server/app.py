"""被测服务（SUT）：游戏服务端 mock（Python 标准库实现，零依赖）。

领域链路：账号登录 -> 创角 -> 角色 / 背包 / 抽卡 / 战斗结算 / 邮件

为什么自己写被测系统：离线可跑、CI 可跑、可现场演示，且能精确控制
概率与数值规则，覆盖游戏测试最关心的考点。

**可测性设计**（面试可讲）：
- 随机可复现：抽卡与暴击支持传入 seed，同一 seed 结果完全一致
- 公式可精确验算：战斗结算可直接指定 crit，不依赖概率即可验证公式
- 数据隔离：每个账号独立角色 / 背包 / 邮件 / 保底计数

HTTP 状态码约定：
- 422 请求形状或类型不合法（缺字段、类型错、超出取值区间）
- 400 业务规则拒绝（钻石不足、道具不足、抽卡次数不支持）
- 401 未鉴权或 Token 失效；404 资源不存在；409 状态冲突（重复创角 / 重复领取）

启动：python -m mock_server.app --port 8123
"""

from __future__ import annotations

import argparse
import json
import os
import random
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable
from urllib.parse import urlparse

from mock_server import rules
from mock_server.store import (
    NICKNAME_MAX_LENGTH,
    STORE,
    TOKEN_TTL_SECONDS,
    DomainError,
)

MAX_SEED = 2**31 - 1


# ---------- 请求校验（纯函数，便于单独复用与测试）----------


def _text(
    payload: dict[str, Any], field: str, *, max_length: int | None = None
) -> tuple[str | None, str | None]:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        return None, f"{field} 必填且必须是非空字符串"
    value = value.strip()
    if max_length is not None and len(value) > max_length:
        return None, f"{field} 长度不能超过 {max_length}"
    return value, None


def _integer(
    payload: dict[str, Any],
    field: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
    default: int | None = None,
    required: bool = True,
) -> tuple[int | None, str | None]:
    if field not in payload:
        if not required:
            return default, None
        return None, f"{field} 必填"
    value = payload[field]
    if isinstance(value, bool) or not isinstance(value, int):
        return None, f"{field} 必须是整数"
    if minimum is not None and value < minimum:
        return None, f"{field} 不能小于 {minimum}"
    if maximum is not None and value > maximum:
        return None, f"{field} 不能大于 {maximum}"
    return value, None


def _number(
    payload: dict[str, Any],
    field: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    default: float | None = None,
    required: bool = True,
) -> tuple[float | None, str | None]:
    if field not in payload:
        if not required:
            return default, None
        return None, f"{field} 必填"
    value = payload[field]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None, f"{field} 必须是数字"
    value = float(value)
    if minimum is not None and value < minimum:
        return None, f"{field} 不能小于 {minimum}"
    if maximum is not None and value > maximum:
        return None, f"{field} 不能大于 {maximum}"
    return value, None


def _validate_battle(payload: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    """战斗结算入参校验；crit 可选，显式指定时跳过随机判定（可测性设计）。"""
    fields: dict[str, Any] = {}
    checks: tuple[tuple[str, dict[str, Any]], ...] = (
        ("atk", {"minimum": 0.0}),
        ("defense", {"minimum": 0.0}),
        ("skill_ratio", {"minimum": 0.0001}),
        ("penetration", {"minimum": 0.0, "maximum": 1.0, "default": 0.0, "required": False}),
        (
            "crit_multiplier",
            {"minimum": 0.0, "default": rules.DEFAULT_CRIT_MULTIPLIER, "required": False},
        ),
        ("damage_bonus", {"minimum": 0.0, "default": 0.0, "required": False}),
        ("crit_rate", {"minimum": 0.0, "maximum": 1.0, "default": 0.0, "required": False}),
    )
    for field, options in checks:
        value, error = _number(payload, field, **options)
        if error:
            return {}, error
        fields[field] = value

    crit = payload.get("crit")
    if crit is not None and not isinstance(crit, bool):
        return {}, "crit 必须是布尔值"
    seed, error = _integer(payload, "seed", minimum=0, maximum=MAX_SEED, required=False)
    if error:
        return {}, error
    fields["crit"] = crit
    fields["seed"] = seed
    return fields, None


class GameApiHandler(BaseHTTPRequestHandler):
    """HTTP 层：路由 + 鉴权 + 入参校验 + 统一响应。"""

    protocol_version = "HTTP/1.1"
    server_version = "MockGameServer/1.0"

    # 请求体是否已被读走：防止 keep-alive 连接被残留字节污染
    _body_read: bool = False

    def handle_one_request(self) -> None:
        # 一个 handler 实例会服务同一连接上的多个请求，标记必须按请求重置
        self._body_read = False
        super().handle_one_request()

    def do_GET(self) -> None:
        self._dispatch(GET_ROUTES)

    def do_POST(self) -> None:
        self._dispatch(POST_ROUTES)

    def do_PUT(self) -> None:
        self._not_found()

    def do_DELETE(self) -> None:
        self._not_found()

    def log_message(self, format: str, *args: Any) -> None:
        if os.environ.get("MOCK_VERBOSE") == "1":
            super().log_message(format, *args)

    # ---------- 分发与响应 ----------

    def _dispatch(self, routes: dict[str, Callable[["GameApiHandler"], None]]) -> None:
        path = urlparse(self.path).path
        handler = routes.get(path)
        if handler is None:
            self._not_found()
            return
        try:
            handler(self)
        except DomainError as exc:
            self._error(exc.http_status, exc.code, exc.message)
        except Exception as exc:  # 兜底：保证被测服务总会返回响应，不吊死客户端
            self._error(500, "INTERNAL_ERROR", f"服务内部错误: {exc}")

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        self._drain_request_body()
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: int, code: str, message: str) -> None:
        self._send_json(status, {"code": code, "message": message})

    def _not_found(self) -> None:
        self._error(404, "NOT_FOUND", f"接口不存在: {urlparse(self.path).path}")

    def _validation_error(self, message: str | None) -> None:
        self._error(422, "VALIDATION_ERROR", message or "请求体非法")

    def _drain_request_body(self) -> None:
        """把未读走的请求体读干净。

        提前返回（401 / 404 / 422）时若跳过这一步，残留字节会被 HTTP/1.1
        keep-alive 的下一次解析当成请求起始行，导致同一连接上后续请求全部 501。
        该 bug 由 tests/integration/test_mock_sut_contract.py 抓出并回归。
        """
        if self._body_read:
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length > 0:
            self.rfile.read(length)
        self._body_read = True

    def _read_json(self) -> tuple[dict[str, Any] | None, str | None]:
        length = int(self.headers.get("Content-Length") or 0)
        if length == 0:
            self._body_read = True
            return {}, None
        raw = self.rfile.read(length)
        self._body_read = True
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None, "请求体不是合法 JSON"
        if not isinstance(payload, dict):
            return None, "请求体必须是 JSON 对象"
        return payload, None

    def _require_auth(self) -> str | None:
        """校验 Bearer Token；失败时自行响应 401 并返回 None。"""
        header = self.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            self._error(401, "UNAUTHORIZED", "缺少 Bearer Token")
            return None
        account = STORE.resolve_token(header[len("Bearer ") :].strip())
        if account is None:
            self._error(401, "UNAUTHORIZED", "Token 无效或已过期")
            return None
        return account

    # ---------- 接口实现 ----------

    def handle_health(self) -> None:
        self._send_json(200, {"status": "ok"})

    def handle_login(self) -> None:
        payload, error = self._read_json()
        if payload is None:
            self._validation_error(error)
            return
        username, error = _text(payload, "username")
        if error:
            self._validation_error(error)
            return
        password, error = _text(payload, "password")
        if error:
            self._validation_error(error)
            return

        token = STORE.login(username, password)
        role = STORE.account_of(username).role
        self._send_json(
            200,
            {
                "token": token,
                "expires_in": TOKEN_TTL_SECONDS,
                "has_role": role is not None,
                "role_id": role.role_id if role else None,
            },
        )

    def handle_logout(self) -> None:
        header = self.headers.get("Authorization", "")
        if self._require_auth() is None:
            return
        STORE.logout(header[len("Bearer ") :].strip())
        self._send_json(200, {"message": "已登出"})

    def handle_role_create(self) -> None:
        account = self._require_auth()
        if account is None:
            return
        payload, error = self._read_json()
        if payload is None:
            self._validation_error(error)
            return
        nickname, error = _text(payload, "nickname", max_length=NICKNAME_MAX_LENGTH)
        if error:
            self._validation_error(error)
            return

        role = STORE.create_role(account, nickname)
        self._send_json(201, role.to_dict())

    def handle_role_get(self) -> None:
        account = self._require_auth()
        if account is None:
            return
        self._send_json(200, STORE.require_role(account).to_dict())

    def handle_bag_get(self) -> None:
        account = self._require_auth()
        if account is None:
            return
        self._send_json(200, STORE.bag_overview(account))

    def handle_bag_use(self) -> None:
        account = self._require_auth()
        if account is None:
            return
        payload, error = self._read_json()
        if payload is None:
            self._validation_error(error)
            return
        item_id, error = _integer(payload, "item_id", minimum=1)
        if error:
            self._validation_error(error)
            return
        count, error = _integer(payload, "count", minimum=1)
        if error:
            self._validation_error(error)
            return

        self._send_json(200, STORE.use_item(account, item_id, count))

    def handle_mail_list(self) -> None:
        account = self._require_auth()
        if account is None:
            return
        self._send_json(200, STORE.list_mails(account))

    def handle_gacha_draw(self) -> None:
        account = self._require_auth()
        if account is None:
            return
        payload, error = self._read_json()
        if payload is None:
            self._validation_error(error)
            return
        times, error = _integer(payload, "times", minimum=1)
        if error:
            self._validation_error(error)
            return
        seed, error = _integer(payload, "seed", minimum=0, maximum=MAX_SEED, required=False)
        if error:
            self._validation_error(error)
            return

        self._send_json(200, STORE.draw_gacha(account, times, seed))

    def handle_battle_settle(self) -> None:
        account = self._require_auth()
        if account is None:
            return
        payload, error = self._read_json()
        if payload is None:
            self._validation_error(error)
            return
        fields, error = _validate_battle(payload)
        if error:
            self._validation_error(error)
            return

        crit = fields.pop("crit")
        seed = fields.pop("seed")
        crit_rate = fields.pop("crit_rate")
        if crit is None:
            rng = random.Random(seed) if seed is not None else random.Random()
            crit = rules.roll_crit(rng, crit_rate)

        damage = rules.compute_damage(**fields, crit=crit)
        self._send_json(200, {"damage": damage, "crit": crit})

    def handle_mail_claim(self) -> None:
        account = self._require_auth()
        if account is None:
            return
        payload, error = self._read_json()
        if payload is None:
            self._validation_error(error)
            return
        mail_id, error = _integer(payload, "mail_id", minimum=1)
        if error:
            self._validation_error(error)
            return

        self._send_json(200, STORE.claim_mail(account, mail_id))


GET_ROUTES: dict[str, Callable[[GameApiHandler], None]] = {
    "/health": GameApiHandler.handle_health,
    "/api/role": GameApiHandler.handle_role_get,
    "/api/bag": GameApiHandler.handle_bag_get,
    "/api/mail": GameApiHandler.handle_mail_list,
}

POST_ROUTES: dict[str, Callable[[GameApiHandler], None]] = {
    "/api/login": GameApiHandler.handle_login,
    "/api/logout": GameApiHandler.handle_logout,
    "/api/role/create": GameApiHandler.handle_role_create,
    "/api/bag/use": GameApiHandler.handle_bag_use,
    "/api/gacha/draw": GameApiHandler.handle_gacha_draw,
    "/api/battle/settle": GameApiHandler.handle_battle_settle,
    "/api/mail/claim": GameApiHandler.handle_mail_claim,
}


def build_server(host: str, port: int) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), GameApiHandler)
    server.daemon_threads = True
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="启动游戏服务端 mock（SUT）")
    parser.add_argument("--host", default=os.environ.get("MOCK_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("MOCK_PORT", "8123")))
    args = parser.parse_args()
    server = build_server(args.host, args.port)
    print(f"[mock-game-server] listening on http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[mock-game-server] shutting down", flush=True)
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()

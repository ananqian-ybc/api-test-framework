"""被测服务（游戏服务端 mock）的契约冒烟脚本：只用标准库，不依赖框架。

用途：改完 SUT 先跑它，30 秒内确认接口契约没被改坏，再跑完整 pytest 套件。
    python scripts/smoke_mock_server.py --base-url http://127.0.0.1:8123
退出码 0 = 全部通过；1 = 有失败项。
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
import uuid
from typing import Any

PASSED: list[str] = []
FAILED: list[str] = []


def call(
    base_url: str,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    token: str | None = None,
) -> tuple[int, Any]:
    """发一次请求，返回 (状态码, 解析后的响应体)。"""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(f"{base_url}{path}", data=data, method=method)
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as error:
        raw = error.read()
        try:
            return error.code, json.loads(raw) if raw else None
        except json.JSONDecodeError:
            return error.code, raw.decode("utf-8", errors="replace")


def check(name: str, actual: Any, expected: Any) -> None:
    if actual == expected:
        PASSED.append(name)
        print(f"  PASS  {name}")
    else:
        FAILED.append(name)
        print(f"  FAIL  {name}: 期望 {expected!r}，实际 {actual!r}")


def login(base_url: str, account: str) -> tuple[int, Any, str | None]:
    status, payload = call(
        base_url, "POST", "/api/login", {"username": account, "password": "Test@123456"}
    )
    return status, payload, payload.get("token") if isinstance(payload, dict) else None


def main() -> int:
    parser = argparse.ArgumentParser(description="游戏服务端 mock 契约冒烟")
    parser.add_argument("--base-url", default="http://127.0.0.1:8123")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    # 每次运行使用全新账号，保证脚本可对同一服务重复执行（幂等）
    run_id = uuid.uuid4().hex[:6]
    account_a = f"sut_a_{run_id}"
    account_b = f"sut_b_{run_id}"

    print("[1] 健康检查与登录鉴权")
    check("health 返回 200", call(base, "GET", "/health")[0], 200)
    check("密码错误返回 401", call(base, "POST", "/api/login", {"username": account_a, "password": "bad"})[0], 401)
    check("缺 password 返回 422", call(base, "POST", "/api/login", {"username": account_a})[0], 422)
    status, payload, token = login(base, account_a)
    check("登录返回 200", status, 200)
    check("新账号尚无角色 has_role=False", payload["has_role"], False)
    check("无 Token 访问角色返回 401", call(base, "GET", "/api/role")[0], 401)
    check("伪造 Token 返回 401", call(base, "GET", "/api/role", token="bogus")[0], 401)

    print("[2] 创角与角色")
    check("未创角查询返回 404", call(base, "GET", "/api/role", token=token)[0], 404)
    status, role = call(base, "POST", "/api/role/create", {"nickname": "冒烟玩家"}, token=token)
    check("创角返回 201", status, 201)
    check("初始等级为 1", role["level"], 1)
    check("初始金币 1000", role["gold"], 1000)
    check("初始钻石 16000", role["diamond"], 16000)
    check("重复创角返回 409", call(base, "POST", "/api/role/create", {"nickname": "再来一次"}, token=token)[0], 409)
    check("昵称超长返回 422", call(base, "POST", "/api/role/create", {"nickname": "很" * 13}, token=token)[0], 422)

    print("[3] 背包与使用道具")
    status, bag = call(base, "GET", "/api/bag", token=token)
    check("背包返回 200", status, 200)
    check("背包容量 100", bag["capacity"], 100)
    check("初始占用 3 格", bag["used"], 3)
    status, used = call(base, "POST", "/api/bag/use", {"item_id": 1, "count": 3}, token=token)
    check("使用道具返回 200", status, 200)
    check("剩余数量 7", used["remain"], 7)
    status, used = call(base, "POST", "/api/bag/use", {"item_id": 3, "count": 1}, token=token)
    check("用光后 remain=0", used["remain"], 0)
    check("用光后格子被移除", call(base, "GET", "/api/bag", token=token)[1]["used"], 2)
    check("道具不存在返回 404", call(base, "POST", "/api/bag/use", {"item_id": 999, "count": 1}, token=token)[0], 404)
    check("数量超持有返回 400", call(base, "POST", "/api/bag/use", {"item_id": 1, "count": 999}, token=token)[0], 400)
    check("count=0 返回 422", call(base, "POST", "/api/bag/use", {"item_id": 1, "count": 0}, token=token)[0], 422)

    print("[4] 抽卡：扣费、确定性、保底、边界")
    status, draw = call(base, "POST", "/api/gacha/draw", {"times": 1, "seed": 20261009}, token=token)
    check("抽卡返回 200", status, 200)
    check("单抽消耗 160 钻石", draw["cost"], 160)
    check("钻石按消耗扣减", draw["diamond"], 16000 - 160)
    check("抽卡结果数量为 1", len(draw["results"]), 1)
    check("times=11 返回 400", call(base, "POST", "/api/gacha/draw", {"times": 11, "seed": 1}, token=token)[0], 400)
    check("times 类型错误返回 422", call(base, "POST", "/api/gacha/draw", {"times": "x"}, token=token)[0], 422)

    status, other, token_b = login(base, account_b)
    call(base, "POST", "/api/role/create", {"nickname": "冒烟玩家B"}, token=token_b)
    status, draw_b = call(base, "POST", "/api/gacha/draw", {"times": 1, "seed": 20261009}, token=token_b)
    check("同 seed 结果可复现", draw_b["results"][0]["rarity"], draw["results"][0]["rarity"])

    print("[5] 战斗结算：公式与边界")
    battle = lambda **kwargs: call(base, "POST", "/api/battle/settle", kwargs, token=token)  # noqa: E731
    check("基础伤害 100*1.0-50=50", battle(atk=100, defense=50, skill_ratio=1.0, crit=False)[1]["damage"], 50)
    check("暴击 50*2.0=100", battle(atk=100, defense=50, skill_ratio=1.0, crit=True)[1]["damage"], 100)
    check("伤害下限为 1", battle(atk=10, defense=1000, skill_ratio=1.0, crit=False)[1]["damage"], 1)
    check("穿透 0.2 生效 1500-400=1100", battle(atk=1000, defense=500, skill_ratio=1.5, penetration=0.2, crit=False)[1]["damage"], 1100)
    check("乘区叠乘后向下取整", battle(atk=1000, defense=500, skill_ratio=1.5, penetration=0.2, crit=True, crit_multiplier=2.5, damage_bonus=0.35)[1]["damage"], 3712)
    check("atk 负数返回 422", battle(atk=-1, defense=0, skill_ratio=1.0)[0], 422)
    check("skill_ratio=0 返回 422", battle(atk=10, defense=0, skill_ratio=0)[0], 422)
    check("penetration=2 返回 422", battle(atk=10, defense=0, skill_ratio=1.0, penetration=2)[0], 422)
    check("crit 非布尔返回 422", battle(atk=10, defense=0, skill_ratio=1.0, crit="yes")[0], 422)

    print("[6] 邮件领取、幂等与账号隔离")
    status, mails = call(base, "GET", "/api/mail", token=token)
    check("邮件列表返回 200", status, 200)
    check("新号有 2 封邮件", mails["total"], 2)
    first_mail = mails["mails"][0]["mail_id"]
    status, claimed = call(base, "POST", "/api/mail/claim", {"mail_id": first_mail}, token=token)
    check("领取邮件返回 200", status, 200)
    check("金币按奖励金额累加", claimed["gold_total"], 1000 + claimed["rewards"]["gold"])
    check("重复领取返回 409", call(base, "POST", "/api/mail/claim", {"mail_id": first_mail}, token=token)[0], 409)
    status, after = call(base, "GET", "/api/mail", token=token)
    check("领取后状态标记为已领取", after["mails"][0]["claimed"], True)
    check("重复领取不重复发货", call(base, "GET", "/api/role", token=token)[1]["gold"], claimed["gold_total"])
    check("邮件不存在返回 404", call(base, "POST", "/api/mail/claim", {"mail_id": 99999999}, token=token)[0], 404)
    check("越权领取他人邮件返回 404", call(base, "POST", "/api/mail/claim", {"mail_id": first_mail}, token=token_b)[0], 404)
    check("另一个账号角色独立", call(base, "GET", "/api/role", token=token_b)[0], 200)
    check("不存在接口返回 404", call(base, "GET", "/api/unknown", token=token)[0], 404)

    print("[7] 登出后 Token 失效")
    check("登出返回 200", call(base, "POST", "/api/logout", {}, token=token)[0], 200)
    check("登出后访问返回 401", call(base, "GET", "/api/role", token=token)[0], 401)

    print(f"\n总计 {len(PASSED) + len(FAILED)} 项：通过 {len(PASSED)}，失败 {len(FAILED)}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())

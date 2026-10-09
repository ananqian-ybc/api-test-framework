"""伤害公式批量校验（AC11）：把"数值对不对"变成一次可重复执行的自动比对。

**为什么独立实现公式**：如果脚本直接 import 被测服务的公式函数，
那么"实现错、验证也错"的情况永远查不出来。这里刻意**重新实现一遍**公式，
两侧同源风险归零——这也是数值测试的标准做法。

两类数据源：
1. `--table`（默认 data/battle_damage_cases.yaml）：人工维护的数值表 + 手算期望值；
2. 边界网格（默认开启）：程序生成参数组合，期望值由本脚本的独立公式计算。

用法：
    .venv\\Scripts\\python.exe scripts/verify_damage_formula.py
    .venv\\Scripts\\python.exe scripts/verify_damage_formula.py --no-grid   # 只跑数值表
退出码 0 = 全部一致；1 = 存在不一致（会打印差异明细）。
"""

from __future__ import annotations

import argparse
import itertools
import math
import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Iterator

import requests
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TABLE = PROJECT_ROOT / "data" / "battle_damage_cases.yaml"
MAX_DIFF_DETAILS = 10


def independent_damage(
    *,
    atk: float,
    defense: float,
    skill_ratio: float,
    penetration: float = 0.0,
    crit: bool = False,
    crit_multiplier: float = 2.0,
    damage_bonus: float = 0.0,
) -> int:
    """独立实现的伤害公式（故意不复用被测服务代码）。

    与公示规则一致：先扣防御（穿透只作用于防御），乘暴击与增伤乘区，
    伤害下限 1，**只在最后一步向下取整**。
    """
    raw = atk * skill_ratio - defense * (1.0 - penetration)
    if raw < 1.0:
        raw = 1.0
    if crit:
        raw = raw * crit_multiplier
    raw = raw * (1.0 + damage_bonus)
    return math.floor(raw)


def grid_cases() -> Iterator[dict[str, Any]]:
    """生成边界网格：0 / 1 / 常规值 / 极大值 × 穿透 / 暴击 / 增伤组合。"""
    atk_values = (0, 1, 100, 999999)
    defense_values = (0, 1, 50, 999999)
    ratio_values = (0.1, 1.0, 2.5)
    penetration_values = (0.0, 0.5, 1.0)
    crit_values = (False, True)
    bonus_values = (0.0, 0.15)
    for atk, defense, ratio, penetration, crit, bonus in itertools.product(
        atk_values, defense_values, ratio_values, penetration_values, crit_values, bonus_values
    ):
        yield {
            "atk": atk,
            "defense": defense,
            "skill_ratio": ratio,
            "penetration": penetration,
            "crit": crit,
            "damage_bonus": bonus,
        }


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start_server(port: int) -> subprocess.Popen[bytes]:
    process = subprocess.Popen(
        [sys.executable, "-m", "mock_server.app", "--port", str(port)],
        cwd=PROJECT_ROOT,
        env={**os.environ},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stderr = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
            raise RuntimeError(f"服务端启动失败：\n{stderr}")
        try:
            if requests.get(f"{base_url}/health", timeout=1).status_code == 200:
                return process
        except requests.RequestException:
            time.sleep(0.2)
    process.kill()
    raise RuntimeError("服务端 15 秒内未就绪")


def settle(base_url: str, token: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = requests.post(
        f"{base_url}/api/battle/settle",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def load_table(path: Path) -> list[dict[str, Any]]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [case for case in raw if "expected_damage" in case]


def verify(base_url: str, token: str, cases: list[tuple[str, dict[str, Any], int]]) -> int:
    mismatches: list[str] = []
    for name, payload, expected in cases:
        actual = settle(base_url, token, payload)["damage"]
        if actual != expected:
            mismatches.append(
                f"{name}: 期望 {expected}，实际 {actual}｜入参 {payload}"
            )

    print(f"共校验 {len(cases)} 组数值")
    if not mismatches:
        print("全部一致：服务端实现与公示公式（独立复算）完全吻合。")
        return 0

    print(f"发现 {len(mismatches)} 处不一致：")
    for detail in mismatches[:MAX_DIFF_DETAILS]:
        print(f"  - {detail}")
    if len(mismatches) > MAX_DIFF_DETAILS:
        print(f"  ... 其余 {len(mismatches) - MAX_DIFF_DETAILS} 处省略")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="伤害公式批量校验")
    parser.add_argument("--table", type=Path, default=DEFAULT_TABLE, help="数值表 YAML 路径")
    parser.add_argument("--no-grid", action="store_true", help="跳过边界网格，只校验数值表")
    parser.add_argument("--base-url", default=None, help="复用已有服务")
    args = parser.parse_args()

    process: subprocess.Popen[bytes] | None = None
    if args.base_url:
        base_url = args.base_url.rstrip("/")
    else:
        port = free_port()
        process = start_server(port)
        base_url = f"http://127.0.0.1:{port}"

    try:
        login = requests.post(
            f"{base_url}/api/login",
            json={"username": f"damage_probe_{uuid.uuid4().hex[:8]}", "password": "Test@123456"},
            timeout=5,
        )
        login.raise_for_status()
        token = login.json()["token"]
        created = requests.post(
            f"{base_url}/api/role/create",
            json={"nickname": "数值校验号"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
        )
        if created.status_code != 201:
            raise RuntimeError(f"创角失败（{created.status_code}）：{created.text}")

        cases: list[tuple[str, dict[str, Any], int]] = []
        if args.table.is_file():
            for case in load_table(args.table):
                payload = {**case["payload"], "crit": case["payload"].get("crit", False)}
                cases.append((case["case_id"], payload, case["expected_damage"]))
            print(f"已加载数值表 {args.table.name}：{len(cases)} 条")
        else:
            print(f"未找到数值表 {args.table}，跳过")

        if not args.no_grid:
            before = len(cases)
            for index, payload in enumerate(grid_cases(), start=1):
                cases.append((f"grid_{index:04d}", payload, independent_damage(**payload)))
            print(f"已生成边界网格：{len(cases) - before} 条")

        return verify(base_url, token, cases)
    finally:
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    sys.exit(main())

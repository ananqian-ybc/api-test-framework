"""抽卡概率大样本统计检验（AC10）。

**为什么不能"抽几次看看"**：
单次或少量抽卡的结果波动极大，靠眼睛看永远得不出结论；而且卡池有 90 抽保底，
保底会**系统性抬高** SSR 的实际比例，直接统计会让 1.6% 的公示概率看起来"被高估"。

因此本脚本：
1. 启动一个**专用**服务端进程，关闭保底（GACHA_PITY_LIMIT 极大）、免消耗（成本 0），
   保证样本独立同分布；
2. 抽 N 次（默认 10000），统计各稀有度的实际频次；
3. 用**卡方拟合优度检验**（自由度 2）判断实际分布与公示概率是否一致；
4. 同时输出各稀有度的 95% 置信区间，便于人工复核。

用法：
    .venv\\Scripts\\python.exe scripts/verify_gacha_probability.py --draws 10000
退出码 0 = 分布与公示概率一致；1 = 存在显著偏差或执行失败。
"""

from __future__ import annotations

import argparse
import math
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PUBLISHED_RATES: dict[str, float] = {"SSR": 0.016, "SR": 0.13, "R": 0.854}
# 卡方临界值：自由度 2，显著性水平 0.001
CHI_SQUARE_CRITICAL_DF2_P001 = 13.8155
Z_95 = 1.96
ACCOUNT = "probability_probe"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start_dedicated_server(port: int) -> subprocess.Popen[bytes]:
    """启动关闭保底、免消耗的专用服务端，保证样本独立同分布。"""
    env = {
        **os.environ,
        "GACHA_PITY_LIMIT": "1000000",  # 关闭保底
        "GACHA_COST_PER_DRAW": "0",  # 免消耗，样本量不受钻石限制
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "mock_server.app", "--port", str(port)],
        cwd=PROJECT_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stderr = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
            raise RuntimeError(f"专用服务端启动失败：\n{stderr}")
        try:
            if requests.get(f"{base_url}/health", timeout=1).status_code == 200:
                return process
        except requests.RequestException:
            time.sleep(0.2)
    process.kill()
    raise RuntimeError("专用服务端 15 秒内未就绪")


def login(base_url: str) -> str:
    response = requests.post(
        f"{base_url}/api/login",
        json={"username": ACCOUNT, "password": "Test@123456"},
        timeout=5,
    )
    response.raise_for_status()
    return response.json()["token"]


def draw_batch(base_url: str, token: str, times: int) -> list[dict]:
    response = requests.post(
        f"{base_url}/api/gacha/draw",
        json={"times": times},
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()["results"]


def chi_square(observed: dict[str, int], total: int) -> float:
    """卡方拟合优度统计量：Σ (O - E)^2 / E。"""
    statistic = 0.0
    for rarity, rate in PUBLISHED_RATES.items():
        expected = total * rate
        statistic += (observed[rarity] - expected) ** 2 / expected
    return statistic


def confidence_interval(hits: int, total: int) -> tuple[float, float]:
    """正态近似的 95% 置信区间。"""
    rate = hits / total
    half_width = Z_95 * math.sqrt(rate * (1 - rate) / total)
    return max(0.0, rate - half_width), min(1.0, rate + half_width)


def main() -> int:
    parser = argparse.ArgumentParser(description="抽卡概率大样本统计检验")
    parser.add_argument("--draws", type=int, default=10000, help="总抽样次数，默认 10000")
    parser.add_argument("--base-url", default=None, help="复用已有服务（需已关闭保底与消耗）")
    args = parser.parse_args()

    process: subprocess.Popen[bytes] | None = None
    if args.base_url:
        base_url = args.base_url.rstrip("/")
    else:
        port = free_port()
        process = start_dedicated_server(port)
        base_url = f"http://127.0.0.1:{port}"

    try:
        token = login(base_url)
        if not requests.post(
            f"{base_url}/api/role/create",
            json={"nickname": "概率检验号"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
        ).ok:
            raise RuntimeError("创角失败（账号可能已存在角色）")

        observed = {rarity: 0 for rarity in PUBLISHED_RATES}
        remaining = args.draws
        while remaining > 0:
            times = 10 if remaining >= 10 else remaining
            for item in draw_batch(base_url, token, times):
                observed[item["rarity"]] += 1
            remaining -= times

        total = sum(observed.values())
        statistic = chi_square(observed, total)

        print(f"样本量: {total}（保底已关闭、消耗为 0，样本独立同分布）")
        print(f"{'稀有度':<6}{'公示概率':>10}{'实际概率':>12}{'95% 置信区间':>24}{'期望次数':>10}{'实际次数':>10}")
        for rarity, rate in PUBLISHED_RATES.items():
            low, high = confidence_interval(observed[rarity], total)
            print(
                f"{rarity:<6}{rate:>10.4f}{observed[rarity] / total:>12.4f}"
                f"{f'[{low:.4f}, {high:.4f}]':>24}{total * rate:>10.1f}{observed[rarity]:>10d}"
            )

        print(f"\n卡方统计量 = {statistic:.4f}（自由度 2，显著性 0.001 的临界值 = {CHI_SQUARE_CRITICAL_DF2_P001}）")
        if statistic <= CHI_SQUARE_CRITICAL_DF2_P001:
            print("结论：实际分布与公示概率无显著差异，概率配置通过检验。")
            return 0
        print("结论：实际分布与公示概率存在显著差异，需排查卡池配置。")
        return 1
    finally:
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    sys.exit(main())

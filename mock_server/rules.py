"""游戏数值与概率规则（纯函数，可独立单元测试与复算）。

**本文件是数值规则的唯一权威来源**，README 中同步公示同一份规则。
`scripts/verify_damage_formula.py` 会独立实现同一公式做交叉验证（故意不复用本文件）。

伤害公式：
    伤害 = floor( max( atk * skill_ratio - defense * (1 - penetration), 1 )
                  * (crit ? crit_multiplier : 1)
                  * (1 + damage_bonus) )

取整规则：**只在最后一步向下取整**，中间结果一律保留浮点，避免多次取整放大误差。
"""

from __future__ import annotations

import math
import os
import random

MIN_DAMAGE = 1.0
DEFAULT_CRIT_MULTIPLIER = 2.0


def int_env(name: str, default: int) -> int:
    """读取整数环境变量；非法值直接报错，避免"静默用默认值"掩盖配置事故。"""
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"环境变量 {name} 必须是整数，实际为 {raw!r}") from None


# 抽卡公示概率（必须与 README 公示一致）
# 保底与消耗可通过环境变量覆盖：概率检验需要"关闭保底、免消耗"的专用配置，
# 否则大样本会被保底机制抬高 SSR 比例，得出错误结论。
PITY_LIMIT = int_env("GACHA_PITY_LIMIT", 90)
GACHA_COST_PER_DRAW = int_env("GACHA_COST_PER_DRAW", 160)
GACHA_ALLOWED_TIMES: tuple[int, ...] = (1, 10)
RARITY_TABLE: tuple[tuple[str, float], ...] = (
    ("SSR", 0.016),
    ("SR", 0.13),
    ("R", 0.854),
)


def compute_damage(
    *,
    atk: float,
    defense: float,
    skill_ratio: float,
    penetration: float = 0.0,
    crit: bool = False,
    crit_multiplier: float = DEFAULT_CRIT_MULTIPLIER,
    damage_bonus: float = 0.0,
) -> int:
    """按公示公式计算伤害（含下限保底与末尾取整）。"""
    base = atk * skill_ratio - defense * (1.0 - penetration)
    base = max(base, MIN_DAMAGE)
    if crit:
        base *= crit_multiplier
    base *= 1.0 + damage_bonus
    return math.floor(base)


def is_pity_draw(pity_counter: int) -> bool:
    """pity_counter 为本次抽卡前累计的「未出 SSR」次数；第 90 抽必出 SSR。"""
    return pity_counter + 1 >= PITY_LIMIT


def roll_rarity(rng: random.Random, pity_counter: int) -> str:
    """按公示概率抽一发；命中保底时直接返回 SSR。"""
    if is_pity_draw(pity_counter):
        return "SSR"
    roll = rng.random()
    cumulative = 0.0
    for rarity, rate in RARITY_TABLE:
        cumulative += rate
        if roll < cumulative:
            return rarity
    return RARITY_TABLE[-1][0]


def roll_crit(rng: random.Random, crit_rate: float) -> bool:
    """按暴击率判定是否暴击。"""
    return rng.random() < crit_rate

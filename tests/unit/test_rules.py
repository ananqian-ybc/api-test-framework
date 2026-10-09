"""数值与概率规则的单元测试。

公式是游戏测试的核心考点：**公式必须被精确锁定**，包括取整方向、
乘区顺序、下限保底、以及浮点误差带来的实际偏差。
"""

from __future__ import annotations

import math
import random

from mock_server.rules import (
    DEFAULT_CRIT_MULTIPLIER,
    GACHA_ALLOWED_TIMES,
    GACHA_COST_PER_DRAW,
    PITY_LIMIT,
    RARITY_TABLE,
    compute_damage,
    is_pity_draw,
    roll_crit,
    roll_rarity,
)


def test_should_compute_base_damage() -> None:
    assert compute_damage(atk=100, defense=50, skill_ratio=1.0) == 50


def test_should_double_damage_on_crit() -> None:
    assert compute_damage(atk=100, defense=50, skill_ratio=1.0, crit=True) == 100


def test_should_keep_minimum_damage_at_one() -> None:
    assert compute_damage(atk=10, defense=1000, skill_ratio=1.0) == 1
    assert compute_damage(atk=0, defense=0, skill_ratio=1.0) == 1


def test_should_apply_penetration_to_defense_only() -> None:
    # 1500 - 500 * (1 - 0.2) = 1500 - 400 = 1100
    assert compute_damage(atk=1000, defense=500, skill_ratio=1.5, penetration=0.2) == 1100


def test_should_multiply_all_zones_then_floor() -> None:
    # 1100 * 2.5 = 2750；2750 * 1.35 = 3712.5 -> 向下取整 3712
    assert (
        compute_damage(
            atk=1000,
            defense=500,
            skill_ratio=1.5,
            penetration=0.2,
            crit=True,
            crit_multiplier=2.5,
            damage_bonus=0.35,
        )
        == 3712
    )


def test_should_floor_only_at_the_end() -> None:
    # 100 - 44.5 = 55.5；暴击 111.0；*1.1 = 122.1 -> 122
    # 若中途取整会变成 floor(55.5)=55 -> 110 -> 121，本用例专门锁死"只在最后取整"
    assert (
        compute_damage(
            atk=100, defense=44.5, skill_ratio=1.0, crit=True, crit_multiplier=2.0, damage_bonus=0.1
        )
        == 122
    )


def test_should_floor_instead_of_rounding() -> None:
    # 55.5 向下取整为 55（不是四舍五入的 56）
    assert compute_damage(atk=100, defense=44.5, skill_ratio=1.0, crit_multiplier=1.0) == 55


def test_should_expose_float_precision_gap_in_bonus() -> None:
    """已知浮点误差，显式锁定而不是假装不存在。

    200 * 1.15 在双精度下是 229.99999999999997，floor 后是 **229**，而数学上是 230。
    这是真实游戏数值问题的典型形态（策划按数学算 230，程序算出 229 少 1 点伤害）。
    要么接受并公示该规则，要么改用整数/定点运算——决策必须有据可依。
    """
    assert 200 * (1.0 + 0.15) < 230
    assert compute_damage(atk=200, defense=0, skill_ratio=1.0, damage_bonus=0.15) == 229


def test_should_survive_huge_values() -> None:
    assert compute_damage(atk=1_000_000_000, defense=0, skill_ratio=1.0) == 1_000_000_000


def test_probability_table_should_sum_to_one() -> None:
    assert math.isclose(sum(rate for _, rate in RARITY_TABLE), 1.0, abs_tol=1e-9)


def test_should_give_ssr_exactly_on_pity_draw() -> None:
    assert is_pity_draw(PITY_LIMIT - 2) is False
    assert is_pity_draw(PITY_LIMIT - 1) is True
    assert roll_rarity(random.Random(1), PITY_LIMIT - 1) == "SSR"


def test_rarity_should_always_come_from_pool() -> None:
    rng = random.Random(20261009)
    allowed = {rarity for rarity, _ in RARITY_TABLE}

    assert {roll_rarity(rng, 0) for _ in range(500)} <= allowed


def test_should_respect_crit_rate_boundaries() -> None:
    assert roll_crit(random.Random(1), 1.0) is True
    assert roll_crit(random.Random(1), 0.0) is False


def test_gacha_constants_should_match_documented_values() -> None:
    assert GACHA_ALLOWED_TIMES == (1, 10)
    assert GACHA_COST_PER_DRAW == 160
    assert DEFAULT_CRIT_MULTIPLIER == 2.0
    assert PITY_LIMIT == 90

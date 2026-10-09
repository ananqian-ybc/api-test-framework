"""战斗结算用例：数值公式验证（游戏测试最核心的专项能力）。

数值表的期望值来自公示公式的独立计算，不由被测代码生成——
否则「验证」与「实现」同源，等于没验证。数值表见 data/battle_damage_cases.yaml。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from common.assertions import assert_json_path, assert_status
from common.data_loader import case_ids, load_cases
from common.http_client import ApiClient
from tests.support.player import Player

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DAMAGE_CASES = load_cases(DATA_DIR / "battle_damage_cases.yaml")
INVALID_CASES = load_cases(DATA_DIR / "battle_invalid_cases.yaml")
BASE_BATTLE = {"atk": 100, "defense": 50, "skill_ratio": 1.0}

pytestmark = pytest.mark.regression


@pytest.mark.parametrize("case", DAMAGE_CASES, ids=case_ids(DAMAGE_CASES))
def test_damage_should_match_documented_formula(player: Player, case: dict) -> None:
    response = player.client.post("/api/battle/settle", json_body=case["payload"])

    assert_status(response, 200)
    assert_json_path(response, "damage", case["expected_damage"])
    assert_json_path(response, "crit", case["payload"]["crit"])


@pytest.mark.negative
@pytest.mark.parametrize("case", INVALID_CASES, ids=case_ids(INVALID_CASES))
def test_should_reject_invalid_battle_payload(player: Player, case: dict) -> None:
    response = player.client.post("/api/battle/settle", json_body=case["payload"])

    assert_status(response, case["expected_status"])


@pytest.mark.smoke
def test_crit_rate_one_should_always_crit(player: Player) -> None:
    response = player.client.post("/api/battle/settle", json_body={**BASE_BATTLE, "crit_rate": 1.0})

    assert_status(response, 200)
    assert_json_path(response, "crit", True)
    assert_json_path(response, "damage", 100)


@pytest.mark.smoke
def test_crit_rate_zero_should_never_crit(player: Player) -> None:
    response = player.client.post("/api/battle/settle", json_body={**BASE_BATTLE, "crit_rate": 0.0})

    assert_status(response, 200)
    assert_json_path(response, "crit", False)
    assert_json_path(response, "damage", 50)


def test_crit_roll_should_be_reproducible_with_seed(player: Player) -> None:
    body = {**BASE_BATTLE, "crit_rate": 0.5, "seed": 1}

    first = player.client.post("/api/battle/settle", json_body=body)
    second = player.client.post("/api/battle/settle", json_body=body)

    assert first.json["crit"] == second.json["crit"], "同 seed 的暴击判定必须一致"


def test_battle_should_not_mutate_role_state(player: Player) -> None:
    """结算接口是纯计算：不应扣体力、改金币或写背包（常见的实现事故）。"""
    before = player.get_role()

    player.client.post("/api/battle/settle", json_body=BASE_BATTLE)

    assert player.get_role() == before


@pytest.mark.negative
def test_should_reject_battle_without_token(raw_client: ApiClient) -> None:
    assert_status(raw_client.post("/api/battle/settle", json_body=BASE_BATTLE), 401)

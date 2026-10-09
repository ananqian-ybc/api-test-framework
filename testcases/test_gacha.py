"""抽卡用例：概率、保底、扣费、可复现性——游戏测试最有特色的一块。

三条主线：
1. 数值契约：单抽 160 / 十连 1600 钻石，失败不得扣费；
2. 随机可测：seed 相同结果必须完全一致（否则回归无法复跑）；
3. 保底承诺：90 抽内必出 SSR，且计数不变量成立。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from common.assertions import assert_json_path, assert_status
from common.data_loader import case_ids, load_cases
from common.http_client import ApiClient
from tests.support.player import Player

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
INVALID_CASES = load_cases(DATA_DIR / "gacha_invalid_cases.yaml")

SINGLE_DRAW_COST = 160
TEN_DRAW_COST = 1600
PITY_LIMIT = 90
INITIAL_DIAMOND = 16000
FIXED_SEED = 20261009

pytestmark = pytest.mark.regression


@pytest.mark.smoke
def test_single_draw_should_cost_160_diamond(player: Player) -> None:
    response = player.client.post("/api/gacha/draw", json_body={"times": 1, "seed": FIXED_SEED})

    assert_status(response, 200)
    assert_json_path(response, "cost", SINGLE_DRAW_COST)
    assert_json_path(response, "diamond", INITIAL_DIAMOND - SINGLE_DRAW_COST)
    assert_json_path(response, "times", 1)
    assert len(response.json["results"]) == 1


@pytest.mark.smoke
def test_ten_draw_should_cost_1600_diamond(player: Player) -> None:
    response = player.client.post("/api/gacha/draw", json_body={"times": 10, "seed": FIXED_SEED})

    assert_status(response, 200)
    assert_json_path(response, "cost", TEN_DRAW_COST)
    assert len(response.json["results"]) == 10
    assert [item["index"] for item in response.json["results"]] == list(range(1, 11))


def test_same_seed_should_produce_identical_results(player: Player, make_player) -> None:
    """随机系统必须留可复现入口，否则失败用例无法复跑，也无法定位。"""
    other = make_player("对照角色")

    first = player.client.post("/api/gacha/draw", json_body={"times": 10, "seed": FIXED_SEED})
    second = other.client.post("/api/gacha/draw", json_body={"times": 10, "seed": FIXED_SEED})

    assert [item["rarity"] for item in first.json["results"]] == [
        item["rarity"] for item in second.json["results"]
    ]
    assert [item["name"] for item in first.json["results"]] == [
        item["name"] for item in second.json["results"]
    ]


@pytest.mark.smoke
def test_should_guarantee_ssr_within_pity_limit(player: Player) -> None:
    """90 抽保底必出 SSR：这是对玩家的硬承诺，也是最容易写错的逻辑。"""
    ssr_count = 0
    longest_drought = 0
    current_drought = 0

    for _ in range(PITY_LIMIT):
        body = player.client.post("/api/gacha/draw", json_body={"times": 1}).json
        if body["results"][0]["rarity"] == "SSR":
            ssr_count += 1
            current_drought = 0
        else:
            current_drought += 1
            longest_drought = max(longest_drought, current_drought)

    assert ssr_count >= 1, f"{PITY_LIMIT} 抽内一次 SSR 都没有，保底未生效"
    assert longest_drought <= PITY_LIMIT - 1, f"连续 {longest_drought} 抽未出 SSR，超出保底上限"


def test_pity_counter_should_follow_invariant(player: Player) -> None:
    """保底计数不变量：出 SSR 归零，未出则 +1。计数错 1 会让保底整体延后/提前。"""
    previous = 0

    for index in range(1, 21):
        body = player.client.post("/api/gacha/draw", json_body={"times": 1}).json
        expected = 0 if body["results"][0]["rarity"] == "SSR" else previous + 1

        assert body["pity_counter"] == expected, f"第 {index} 抽保底计数不符：{body}"
        previous = body["pity_counter"]


@pytest.mark.negative
def test_should_reject_draw_when_diamond_not_enough(player: Player) -> None:
    """16000 钻石刚好够 10 次十连，第 11 次应被拒绝且不扣费。"""
    for _ in range(INITIAL_DIAMOND // TEN_DRAW_COST):
        assert_status(player.client.post("/api/gacha/draw", json_body={"times": 10}), 200)

    response = player.client.post("/api/gacha/draw", json_body={"times": 10})

    assert_status(response, 400)
    assert_json_path(response, "code", "NOT_ENOUGH_DIAMOND")
    assert player.get_role()["diamond"] == 0, "失败的抽卡不得改变钻石"


@pytest.mark.negative
@pytest.mark.parametrize("case", INVALID_CASES, ids=case_ids(INVALID_CASES))
def test_should_reject_invalid_draw_payload(player: Player, case: dict) -> None:
    response = player.client.post("/api/gacha/draw", json_body=case["payload"])

    assert_status(response, case["expected_status"])


@pytest.mark.negative
def test_should_reject_draw_without_token(raw_client: ApiClient) -> None:
    assert_status(raw_client.post("/api/gacha/draw", json_body={"times": 1}), 401)

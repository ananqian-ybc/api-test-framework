"""背包与道具使用用例：数量边界是这里最容易出 bug 的地方。

覆盖：初始数据、部分使用、用光释放格子、超量使用、非法参数、失败不改数据。
"""

from __future__ import annotations

import pytest

from common.assertions import assert_json_path, assert_status
from common.http_client import ApiClient
from tests.support.player import Player

INITIAL_ITEM_IDS = [1, 2, 3]
pytestmark = pytest.mark.regression


@pytest.mark.smoke
def test_should_return_initial_bag(player: Player) -> None:
    bag = player.get_bag()

    assert bag["capacity"] == 100
    assert bag["used"] == 3
    assert [item["item_id"] for item in bag["items"]] == INITIAL_ITEM_IDS, "背包应按道具 ID 排序"
    assert bag["items"][0] == {
        "item_id": 1,
        "name": "小血瓶",
        "count": 10,
        "stack_limit": 999,
        "bound": True,
    }


@pytest.mark.smoke
def test_should_reduce_count_when_using_part_of_stack(player: Player) -> None:
    response = player.client.post("/api/bag/use", json_body={"item_id": 1, "count": 3})

    assert_status(response, 200)
    assert_json_path(response, "remain", 7)
    counts = {item["item_id"]: item["count"] for item in player.get_bag()["items"]}
    assert counts[1] == 7


def test_should_remove_slot_when_stack_is_used_up(player: Player) -> None:
    response = player.client.post("/api/bag/use", json_body={"item_id": 2, "count": 5})

    assert_status(response, 200)
    assert_json_path(response, "remain", 0)
    bag = player.get_bag()
    assert 2 not in [item["item_id"] for item in bag["items"]], "用光后应释放格子"
    assert bag["used"] == 2


def test_should_allow_using_exact_owned_count(player: Player) -> None:
    """边界值：正好等于持有数量必须成功（off-by-one 高发点）。"""
    response = player.client.post("/api/bag/use", json_body={"item_id": 3, "count": 1})

    assert_status(response, 200)
    assert_json_path(response, "remain", 0)


@pytest.mark.negative
def test_should_reject_using_more_than_owned(player: Player) -> None:
    response = player.client.post("/api/bag/use", json_body={"item_id": 1, "count": 11})

    assert_status(response, 400)
    assert_json_path(response, "code", "NOT_ENOUGH_ITEM")
    counts = {item["item_id"]: item["count"] for item in player.get_bag()["items"]}
    assert counts[1] == 10, "失败的请求不得改变道具数量（无副作用）"


@pytest.mark.negative
def test_should_reject_unknown_item(player: Player) -> None:
    response = player.client.post("/api/bag/use", json_body={"item_id": 999, "count": 1})

    assert_status(response, 404)
    assert_json_path(response, "code", "ITEM_NOT_FOUND")


@pytest.mark.negative
@pytest.mark.parametrize(
    "payload",
    [
        {"item_id": 1, "count": 0},
        {"item_id": 1, "count": -1},
        {"item_id": "1", "count": 1},
        {"item_id": 1},
        {},
    ],
    ids=["count_zero", "count_negative", "item_id_string", "count_missing", "all_missing"],
)
def test_should_reject_invalid_use_payload(player: Player, payload: dict) -> None:
    assert_status(player.client.post("/api/bag/use", json_body=payload), 422)


@pytest.mark.negative
def test_should_reject_bag_access_without_token(raw_client: ApiClient) -> None:
    assert_status(raw_client.get("/api/bag"), 401)

"""登录与创角用例：鉴权、初始数值、唯一性、账号隔离。

游戏测试关注点：新号初始数值是否与策划案一致、重复创角是否被拦、
账号之间数据会不会串味（串号是线上最严重的事故之一）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from common.assertions import assert_json_contains, assert_json_path, assert_status
from common.data_loader import case_ids, load_cases
from common.http_client import ApiClient
from mock_server.store import TEST_PASSWORD
from tests.support.player import Player

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
LOGIN_CASES = load_cases(DATA_DIR / "login_cases.yaml")
ROLE_CASES = load_cases(DATA_DIR / "role_cases.yaml")

pytestmark = pytest.mark.regression


@pytest.mark.negative
@pytest.mark.parametrize("case", LOGIN_CASES, ids=case_ids(LOGIN_CASES))
def test_login_should_reject_invalid_payload(raw_client: ApiClient, case: dict) -> None:
    response = raw_client.post("/api/login", json_body=case["payload"], auth=False)

    assert_status(response, case["expected_status"])


@pytest.mark.smoke
def test_should_login_new_account_without_role(raw_client: ApiClient, unique_account) -> None:
    account = unique_account("login")

    response = raw_client.post(
        "/api/login", json_body={"username": account, "password": TEST_PASSWORD}, auth=False
    )

    assert_status(response, 200)
    assert_json_contains(response, {"has_role": False, "role_id": None})
    assert len(response.json["token"]) == 32, "Token 应为 32 位十六进制串"


def test_should_issue_new_token_on_each_login(raw_client: ApiClient, unique_account) -> None:
    account = unique_account("login")
    body = {"username": account, "password": TEST_PASSWORD}

    first = raw_client.post("/api/login", json_body=body, auth=False).json["token"]
    second = raw_client.post("/api/login", json_body=body, auth=False).json["token"]

    assert first != second, "同一账号多次登录应签发不同 Token"


@pytest.mark.smoke
def test_should_create_role_with_documented_initial_values(player: Player) -> None:
    """新号初始数值是策划案写死的，必须逐项核对，不能只看接口返回 201。"""
    assert player.role["level"] == 1
    assert player.role["gold"] == 1000
    assert player.role["diamond"] == 16000
    assert player.role["stamina"] == 120
    assert player.role["pity_counter"] == 0
    assert player.role["nickname"] == "自动化测试角色"

    assert player.get_role() == player.role, "重新查询应与创角返回一致（数据已落库）"


@pytest.mark.negative
@pytest.mark.parametrize("case", ROLE_CASES, ids=case_ids(ROLE_CASES))
def test_role_create_should_validate_nickname(account_client, case: dict) -> None:
    """昵称规则：必填、非空白、长度上限 12，边界值 12 必须放行。"""
    response = account_client().post("/api/role/create", json_body=case["payload"])

    assert_status(response, case["expected_status"])


@pytest.mark.negative
def test_should_reject_duplicate_role_creation(player: Player) -> None:
    response = player.client.post("/api/role/create", json_body={"nickname": "第二个角色"})

    assert_status(response, 409)
    assert_json_path(response, "code", "ROLE_EXISTS")


@pytest.mark.negative
def test_should_return_404_when_role_not_created(account_client) -> None:
    response = account_client().get("/api/role")

    assert_status(response, 404)
    assert_json_path(response, "code", "ROLE_NOT_FOUND")


@pytest.mark.negative
def test_should_reject_request_without_token(raw_client: ApiClient) -> None:
    assert_status(raw_client.get("/api/role"), 401)


@pytest.mark.negative
def test_should_reject_stale_token_after_logout(player: Player, raw_client: ApiClient) -> None:
    """登出后服务端 Token 立即失效。

    注意与「客户端 401 自动重登」区分：那条用例验证客户端会自愈，
    这条验证服务端确实把 Token 作废了，两者不可互相替代。
    """
    stale_token = player.token_manager.get_token()
    assert_status(player.client.post("/api/logout"), 200)

    response = raw_client.get(
        "/api/role", headers={"Authorization": f"Bearer {stale_token}"}, auth=False
    )

    assert_status(response, 401)
    assert_json_path(response, "code", "UNAUTHORIZED")


@pytest.mark.smoke
def test_should_isolate_data_between_accounts(player: Player, make_player) -> None:
    other = make_player("隔离验证角色")

    assert player.role_id != other.role_id
    player.client.post("/api/gacha/draw", json_body={"times": 1})

    assert other.get_role()["diamond"] == 16000, "A 账号抽卡不应影响 B 账号"

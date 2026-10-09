"""邮件用例：重复领取幂等与账号隔离。

与线上「发货失败 / 重复到货」问题同构：奖励发放必须幂等，
越权领取必须被拦截，失败请求必须无副作用。
"""

from __future__ import annotations

import pytest

from common.assertions import assert_json_path, assert_status
from common.http_client import ApiClient
from tests.support.player import Player

INITIAL_GOLD = 1000
pytestmark = pytest.mark.regression


@pytest.mark.smoke
def test_should_list_two_unclaimed_mails_for_new_player(player: Player) -> None:
    mails = player.get_mails()

    assert len(mails) == 2
    assert all(mail["claimed"] is False for mail in mails)
    assert {mail["gold"] for mail in mails} == {500, 300}


@pytest.mark.smoke
def test_should_grant_reward_on_first_claim(player: Player) -> None:
    mail = player.get_mails()[0]

    response = player.client.post("/api/mail/claim", json_body={"mail_id": mail["mail_id"]})

    assert_status(response, 200)
    assert_json_path(response, "rewards.gold", mail["gold"])
    assert_json_path(response, "gold_total", INITIAL_GOLD + mail["gold"])
    assert player.get_role()["gold"] == INITIAL_GOLD + mail["gold"]


def test_should_mark_mail_as_claimed(player: Player) -> None:
    mail = player.get_mails()[0]

    player.client.post("/api/mail/claim", json_body={"mail_id": mail["mail_id"]})

    claimed_states = {item["mail_id"]: item["claimed"] for item in player.get_mails()}
    assert claimed_states[mail["mail_id"]] is True
    assert sum(1 for state in claimed_states.values() if state) == 1


@pytest.mark.negative
def test_should_reject_duplicate_claim_and_keep_gold(player: Player) -> None:
    """幂等核心：重复领取必须被拒绝，且金币不得重复到账。"""
    mail = player.get_mails()[0]
    player.client.post("/api/mail/claim", json_body={"mail_id": mail["mail_id"]})
    gold_after_first_claim = player.get_role()["gold"]

    response = player.client.post("/api/mail/claim", json_body={"mail_id": mail["mail_id"]})

    assert_status(response, 409)
    assert_json_path(response, "code", "MAIL_ALREADY_CLAIMED")
    assert player.get_role()["gold"] == gold_after_first_claim, "重复领取不得重复发货"


@pytest.mark.negative
def test_should_reject_unknown_mail(player: Player) -> None:
    response = player.client.post("/api/mail/claim", json_body={"mail_id": 99999999})

    assert_status(response, 404)
    assert_json_path(response, "code", "MAIL_NOT_FOUND")


@pytest.mark.negative
def test_should_reject_claiming_other_players_mail(player: Player, make_player) -> None:
    """越权隔离：B 账号即使拿到 A 账号的 mail_id 也不能领取。"""
    other = make_player("越权验证角色")
    victim_mail_id = player.get_mails()[0]["mail_id"]

    response = other.client.post("/api/mail/claim", json_body={"mail_id": victim_mail_id})

    assert_status(response, 404)
    assert other.get_role()["gold"] == INITIAL_GOLD


@pytest.mark.negative
@pytest.mark.parametrize(
    "payload",
    [{"mail_id": 0}, {"mail_id": -1}, {"mail_id": "1"}, {}],
    ids=["mail_id_zero", "mail_id_negative", "mail_id_string", "mail_id_missing"],
)
def test_should_reject_invalid_claim_payload(player: Player, payload: dict) -> None:
    assert_status(player.client.post("/api/mail/claim", json_body=payload), 422)


@pytest.mark.negative
def test_should_reject_mail_access_without_token(raw_client: ApiClient) -> None:
    assert_status(raw_client.get("/api/mail"), 401)

"""游戏服务端内存数据与业务规则。

分层意图：本文件只管「游戏规则」，不碰 HTTP；违反规则时抛 DomainError，
由 HTTP 层映射成状态码。这样规则可以被单元测试直接覆盖，不需要起服务。
"""

from __future__ import annotations

import random
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from mock_server.rules import (
    GACHA_ALLOWED_TIMES,
    GACHA_COST_PER_DRAW,
    roll_rarity,
)

TEST_PASSWORD = "Test@123456"
TOKEN_TTL_SECONDS = 3600
NICKNAME_MAX_LENGTH = 12

INITIAL_GOLD = 1000
INITIAL_DIAMOND = 16000
INITIAL_STAMINA = 120
INITIAL_LEVEL = 1
BAG_CAPACITY = 100

RARITY_POOLS: dict[str, tuple[str, ...]] = {
    "SSR": ("五星角色·炎狱剑姬", "五星角色·霜华"),
    "SR": ("四星角色·铁卫", "四星武器·裂风"),
    "R": ("三星武器·短刃", "三星材料·精铁"),
}


class DomainError(Exception):
    """游戏规则被违反。code 写入响应体，http_status 由 HTTP 层决定。"""

    def __init__(self, code: str, message: str, http_status: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


def _conflict(code: str, message: str) -> DomainError:
    return DomainError(code, message, 409)


def _not_found(code: str, message: str) -> DomainError:
    return DomainError(code, message, 404)


def _bad_request(code: str, message: str) -> DomainError:
    return DomainError(code, message, 400)


@dataclass
class BagItem:
    item_id: int
    name: str
    count: int
    stack_limit: int
    bound: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "item_id": self.item_id,
            "name": self.name,
            "count": self.count,
            "stack_limit": self.stack_limit,
            "bound": self.bound,
        }


@dataclass
class Mail:
    mail_id: int
    title: str
    gold: int
    claimed: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "mail_id": self.mail_id,
            "title": self.title,
            "gold": self.gold,
            "claimed": self.claimed,
        }


@dataclass
class Role:
    role_id: int
    nickname: str
    level: int = INITIAL_LEVEL
    gold: int = INITIAL_GOLD
    diamond: int = INITIAL_DIAMOND
    stamina: int = INITIAL_STAMINA
    pity_counter: int = 0
    bag: dict[int, BagItem] = field(default_factory=dict)
    mails: dict[int, Mail] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "role_id": self.role_id,
            "nickname": self.nickname,
            "level": self.level,
            "gold": self.gold,
            "diamond": self.diamond,
            "stamina": self.stamina,
            "pity_counter": self.pity_counter,
        }


@dataclass
class Account:
    name: str
    role: Role | None = None


class GameStore:
    """线程安全的内存游戏服务端。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._accounts: dict[str, Account] = {}
        self._tokens: dict[str, tuple[str, datetime]] = {}
        self._next_role_id = 10001
        self._next_mail_id = 1

    # ---------- 账号与鉴权 ----------

    def login(self, account_name: str, password: str) -> str:
        if password != TEST_PASSWORD:
            raise DomainError("AUTH_FAILED", "账号或密码错误", 401)
        with self._lock:
            account = self._accounts.setdefault(account_name, Account(account_name))
            token = uuid.uuid4().hex
            self._tokens[token] = (
                account.name,
                datetime.now(timezone.utc) + timedelta(seconds=TOKEN_TTL_SECONDS),
            )
            return token

    def logout(self, token: str) -> None:
        with self._lock:
            self._tokens.pop(token, None)

    def resolve_token(self, token: str) -> str | None:
        with self._lock:
            entry = self._tokens.get(token)
            if entry is None:
                return None
            account_name, expires_at = entry
            if expires_at <= datetime.now(timezone.utc):
                self._tokens.pop(token, None)
                return None
            return account_name

    def account_of(self, account_name: str) -> Account:
        with self._lock:
            return self._accounts.setdefault(account_name, Account(account_name))

    def require_role(self, account_name: str) -> Role:
        role = self.account_of(account_name).role
        if role is None:
            raise _not_found("ROLE_NOT_FOUND", "角色不存在，请先创角")
        return role

    # ---------- 创角与角色 ----------

    def create_role(self, account_name: str, nickname: str) -> Role:
        with self._lock:
            account = self.account_of(account_name)
            if account.role is not None:
                raise _conflict("ROLE_EXISTS", "该账号已创建角色")
            role = Role(role_id=self._next_role_id, nickname=nickname)
            self._next_role_id += 1
            role.bag = {
                1: BagItem(1, "小血瓶", 10, 999, bound=True),
                2: BagItem(2, "经验药水", 5, 999, bound=False),
                3: BagItem(3, "稀有武器·裂风", 1, 1, bound=True),
            }
            role.mails = {
                self._next_mail_id: Mail(self._next_mail_id, "新手礼包", 500),
                self._next_mail_id + 1: Mail(self._next_mail_id + 1, "七日登录奖励", 300),
            }
            self._next_mail_id += 2
            account.role = role
            return role

    # ---------- 背包 ----------

    def bag_overview(self, account_name: str) -> dict[str, object]:
        role = self.require_role(account_name)
        with self._lock:
            items = [item.to_dict() for item in sorted(role.bag.values(), key=lambda i: i.item_id)]
            return {"capacity": BAG_CAPACITY, "used": len(items), "items": items}

    def use_item(self, account_name: str, item_id: int, count: int) -> dict[str, object]:
        role = self.require_role(account_name)
        with self._lock:
            item = role.bag.get(item_id)
            if item is None:
                raise _not_found("ITEM_NOT_FOUND", f"背包中不存在道具 {item_id}")
            if count > item.count:
                raise _bad_request(
                    "NOT_ENOUGH_ITEM", f"道具数量不足：持有 {item.count}，需要使用 {count}"
                )
            item.count -= count
            if item.count == 0:
                del role.bag[item_id]
                remain = 0
            else:
                remain = item.count
            return {"item_id": item_id, "used": count, "remain": remain}

    # ---------- 抽卡 ----------

    def draw_gacha(
        self, account_name: str, times: int, seed: int | None
    ) -> dict[str, object]:
        if times not in GACHA_ALLOWED_TIMES:
            raise _bad_request("INVALID_TIMES", f"times 只支持 {GACHA_ALLOWED_TIMES}")
        role = self.require_role(account_name)
        cost = GACHA_COST_PER_DRAW * times
        with self._lock:
            if role.diamond < cost:
                raise _bad_request(
                    "NOT_ENOUGH_DIAMOND", f"钻石不足：持有 {role.diamond}，需要 {cost}"
                )
            rng = random.Random(seed) if seed is not None else random.Random()
            results: list[dict[str, object]] = []
            for index in range(1, times + 1):
                rarity = roll_rarity(rng, role.pity_counter)
                role.pity_counter = 0 if rarity == "SSR" else role.pity_counter + 1
                results.append(
                    {
                        "index": index,
                        "rarity": rarity,
                        "name": rng.choice(RARITY_POOLS[rarity]),
                        "pity_counter": role.pity_counter,
                    }
                )
            role.diamond -= cost
            ssr_count = sum(1 for item in results if item["rarity"] == "SSR")
            return {
                "times": times,
                "cost": cost,
                "diamond": role.diamond,
                "pity_counter": role.pity_counter,
                "ssr_count": ssr_count,
                "results": results,
            }

    # ---------- 邮件 ----------

    def list_mails(self, account_name: str) -> dict[str, object]:
        """邮件列表：用例需要靠它发现 mail_id 并校验领取状态。"""
        role = self.require_role(account_name)
        with self._lock:
            mails = [mail.to_dict() for mail in sorted(role.mails.values(), key=lambda m: m.mail_id)]
            return {"total": len(mails), "mails": mails}

    def claim_mail(self, account_name: str, mail_id: int) -> dict[str, object]:
        role = self.require_role(account_name)
        with self._lock:
            mail = role.mails.get(mail_id)
            if mail is None:
                raise _not_found("MAIL_NOT_FOUND", f"邮件 {mail_id} 不存在")
            if mail.claimed:
                raise _conflict("MAIL_ALREADY_CLAIMED", f"邮件 {mail_id} 已领取，请勿重复领取")
            mail.claimed = True
            role.gold += mail.gold
            return {
                "mail_id": mail_id,
                "title": mail.title,
                "rewards": {"gold": mail.gold},
                "gold_total": role.gold,
            }


STORE = GameStore()

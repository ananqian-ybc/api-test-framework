"""被测服务（mock SUT）的协议契约回归测试。

这里记录的是用例真正抓到过的问题，而不是凭空补的覆盖率：

**keep-alive 连接被残留请求体污染**
服务端在"提前返回"（鉴权失败 401、参数校验失败 422）时如果没把请求体从
socket 读走，残留字节会被 HTTP/1.1 keep-alive 的下一次解析当成请求起始行，
于是同一个连接上的后续请求全部返回 501 Unsupported method。
这类问题在长连接、连接池复用的真实服务里非常常见，且只在"同一个连接连续发请求"
时才出现——单条用例永远测不出来。
"""

from __future__ import annotations

import requests

from common.settings import Settings
from mock_server.store import TEST_PASSWORD


def test_should_keep_connection_usable_after_early_401_return(settings: Settings) -> None:
    """先收到 401（服务端未读请求体），同一连接上的下一个请求仍必须被正确处理。"""
    session = requests.Session()
    try:
        unauthorized = session.post(
            f"{settings.base_url}/api/bag/use",  # 带请求体，但服务端在鉴权阶段就返回 401
            json={"item_id": 1, "count": 1},
            timeout=settings.timeout,
        )
        assert unauthorized.status_code == 401, unauthorized.text

        follow_up = session.post(
            f"{settings.base_url}/api/login",
            json={"username": "contract_probe", "password": TEST_PASSWORD},
            timeout=settings.timeout,
        )
        assert follow_up.status_code == 200, follow_up.text
        assert "token" in follow_up.json()
    finally:
        session.close()


def test_should_keep_connection_usable_after_early_422_return(settings: Settings) -> None:
    """参数校验失败返回 422 后，同一连接上的下一个请求也必须被正确处理。

    注：登录接口在返回 422 前已经读过请求体，因此这条用例是防护性的契约检查，
    与上面 401 那条（复现真实 bug）配对，覆盖"提前返回"的两类分支。
    """
    session = requests.Session()
    try:
        invalid = session.post(
            f"{settings.base_url}/api/login",
            json={"username": "contract_probe"},
            timeout=settings.timeout,
        )
        assert invalid.status_code == 422, invalid.text

        follow_up = session.get(f"{settings.base_url}/health", timeout=settings.timeout)
        assert follow_up.status_code == 200, follow_up.text
    finally:
        session.close()

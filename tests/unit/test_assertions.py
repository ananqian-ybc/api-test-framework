"""断言封装的单元测试：重点验证失败信息是否足以定位问题。"""

from __future__ import annotations

import pytest

from common.assertions import assert_json_contains, assert_json_path, assert_status
from common.http_client import ApiResponse


def _response(
    status_code: int = 200,
    text: str = '{"code": "OK", "items": [{"title": "预置任务 01"}]}',
    method: str = "GET",
    url: str = "http://127.0.0.1:8123/api/tasks?page=1",
    request_body: object = None,
) -> ApiResponse:
    return ApiResponse(
        method=method,
        url=url,
        status_code=status_code,
        headers={"Content-Type": "application/json"},
        text=text,
        elapsed_ms=12.5,
        request_body=request_body,
    )


def test_should_pass_when_status_matches() -> None:
    assert_status(_response(201), 201)


def test_should_report_expected_and_actual_when_status_differs() -> None:
    with pytest.raises(AssertionError) as error:
        assert_status(_response(404), 200)

    assert "200" in str(error.value)
    assert "404" in str(error.value)


def test_should_include_full_request_and_response_in_failure_message() -> None:
    response = _response(status_code=422, text='{"code": "VALIDATION_ERROR"}', request_body={"title": ""})

    with pytest.raises(AssertionError) as error:
        assert_status(response, 201)

    message = str(error.value)
    assert "GET" in message
    assert "http://127.0.0.1:8123/api/tasks?page=1" in message
    assert '{"title": ""}' in message
    assert "422" in message
    assert 'VALIDATION_ERROR' in message


def test_should_read_value_on_dotted_path() -> None:
    assert_json_path(_response(), "items.0.title", "预置任务 01")
    assert_json_path(_response(), "code", "OK")


def test_should_report_missing_field_with_full_body() -> None:
    with pytest.raises(AssertionError) as error:
        assert_json_path(_response(), "items.5.title", "不存在")

    message = str(error.value)
    assert "路径不存在" in message
    assert "items.5.title" in message
    assert "预置任务 01" in message


def test_should_report_value_mismatch_with_full_body() -> None:
    with pytest.raises(AssertionError) as error:
        assert_json_path(_response(), "code", "FAIL")

    message = str(error.value)
    assert "OK" in message
    assert "FAIL" in message


def test_should_fail_clearly_when_body_is_not_json() -> None:
    with pytest.raises(AssertionError) as error:
        assert_json_path(_response(text="<html>500</html>"), "code", "OK")

    assert "不是合法 JSON" in str(error.value)


def test_should_check_subset_of_json_body() -> None:
    assert_json_contains(_response(), {"code": "OK"})


def test_should_report_missing_subset_key() -> None:
    with pytest.raises(AssertionError) as error:
        assert_json_contains(_response(), {"code": "OK", "total": 25})

    message = str(error.value)
    assert "total" in message
    assert "缺少字段" in message

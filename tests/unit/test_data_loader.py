"""测试数据加载的单元测试（不依赖网络）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from common.data_loader import case_ids, load_cases, load_yaml
from common.exceptions import DataError

CASES_YAML = """
- case_id: login_success
  title: 正确用户名密码
  expected_status: 200
- title: 缺少密码
  expected_status: 422
"""


def _write(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def test_should_load_records_and_keep_explicit_case_id(tmp_path: Path) -> None:
    cases = load_cases(_write(tmp_path, "auth.yaml", CASES_YAML))

    assert len(cases) == 2
    assert cases[0]["case_id"] == "login_success"
    assert cases[0]["expected_status"] == 200


def test_should_inject_case_id_when_missing(tmp_path: Path) -> None:
    cases = load_cases(_write(tmp_path, "auth.yaml", CASES_YAML))

    assert cases[1]["case_id"] == "auth-2"


def test_should_return_case_ids_for_parametrize(tmp_path: Path) -> None:
    cases = load_cases(_write(tmp_path, "auth.yaml", CASES_YAML))

    assert case_ids(cases) == ["login_success", "auth-2"]


def test_should_load_plain_yaml_file(tmp_path: Path) -> None:
    payload = load_yaml(_write(tmp_path, "plain.yaml", "base_url: http://x\n"))

    assert payload == {"base_url": "http://x"}


def test_should_raise_clear_error_when_file_missing(tmp_path: Path) -> None:
    with pytest.raises(DataError, match="数据文件不存在"):
        load_cases(tmp_path / "not-exists.yaml")


def test_should_raise_clear_error_when_yaml_is_malformed(tmp_path: Path) -> None:
    with pytest.raises(DataError, match="YAML"):
        load_cases(_write(tmp_path, "broken.yaml", "- title: [unclosed\n"))


def test_should_raise_clear_error_when_root_is_not_list(tmp_path: Path) -> None:
    with pytest.raises(DataError, match="必须是列表"):
        load_cases(_write(tmp_path, "mapping.yaml", "title: 不是列表\n"))


def test_should_raise_clear_error_when_record_is_not_mapping(tmp_path: Path) -> None:
    with pytest.raises(DataError, match="必须是字典"):
        load_cases(_write(tmp_path, "scalar.yaml", "- 只是一个字符串\n"))


def test_should_raise_clear_error_when_case_id_duplicated(tmp_path: Path) -> None:
    duplicated = "- case_id: same\n  a: 1\n- case_id: same\n  a: 2\n"

    with pytest.raises(DataError, match="case_id 重复"):
        load_cases(_write(tmp_path, "dup.yaml", duplicated))

"""YAML 测试数据加载：数据与代码分离，用例只描述"输入 -> 期望输出"。

每条数据必须有唯一 case_id：它是报告里的用例名，也是失败时的定位线索。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from common.exceptions import DataError

CASE_ID_FIELD = "case_id"


def load_yaml(path: Path | str) -> Any:
    """读取 YAML 文件；文件缺失或语法错误时抛出带路径的可读错误。"""
    file_path = Path(path)
    if not file_path.is_file():
        raise DataError(f"数据文件不存在: {file_path}")
    try:
        return yaml.safe_load(file_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise DataError(f"数据文件 YAML 解析失败: {file_path}\n{exc}") from exc


def load_cases(path: Path | str) -> list[dict[str, Any]]:
    """读取用例列表；缺失 case_id 时按"文件名-序号"自动注入，并拒绝重复。"""
    file_path = Path(path)
    raw = load_yaml(file_path)
    if not isinstance(raw, list):
        raise DataError(f"数据文件必须是列表（每条一个用例）: {file_path}")

    cases: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, record in enumerate(raw, start=1):
        if not isinstance(record, dict):
            raise DataError(f"数据文件第 {index} 条必须是字典: {file_path}")
        case = dict(record)
        case.setdefault(CASE_ID_FIELD, f"{file_path.stem}-{index}")
        case_id = str(case[CASE_ID_FIELD])
        if case_id in seen:
            raise DataError(f"case_id 重复: {case_id}（{file_path}）")
        seen.add(case_id)
        cases.append(case)
    return cases


def case_ids(cases: list[dict[str, Any]]) -> list[str]:
    """提取 case_id 列表，供 pytest.mark.parametrize 的 ids 使用。"""
    return [str(case[CASE_ID_FIELD]) for case in cases]

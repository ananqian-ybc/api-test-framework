"""日志模块的单元测试。"""

from __future__ import annotations

import logging
from pathlib import Path

from common.logger import get_logger


def test_should_write_message_into_log_file(tmp_path: Path) -> None:
    logger = get_logger("unit-logger", log_dir=tmp_path)

    logger.info("回归开始")
    for handler in logger.handlers:
        handler.flush()

    log_files = list(tmp_path.glob("unit-logger-*.log"))
    assert len(log_files) == 1, f"应只产生一个日志文件，实际 {log_files}"
    assert "回归开始" in log_files[0].read_text(encoding="utf-8")


def test_should_not_duplicate_handlers_on_repeated_calls(tmp_path: Path) -> None:
    first = get_logger("dup-logger", log_dir=tmp_path)
    handler_count = len(first.handlers)

    second = get_logger("dup-logger", log_dir=tmp_path)

    assert second is first
    assert len(second.handlers) == handler_count == 2, "应为文件 + 终端两个 handler，且不重复挂载"


def test_should_not_propagate_to_root_logger(tmp_path: Path) -> None:
    logger = get_logger("quiet-logger", log_dir=tmp_path)

    assert logger.propagate is False, "避免日志被 root logger 重复输出"


def test_should_default_to_project_logs_dir() -> None:
    logger = get_logger("default-dir-logger")

    log_dir = Path(str(logger.handlers[0].baseFilename)).parent

    assert log_dir.name == "logs"
    assert logger.level == logging.INFO

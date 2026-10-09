"""结构化日志：文件 + 终端双输出，按运行时间戳落盘便于回溯。

设计取舍：
- 同名 logger 重复调用直接复用，避免 pytest 多模块导入时重复挂 handler 导致日志重复；
- propagate=False，防止日志被 root logger 再输出一遍；
- 文件强制 UTF-8，避免 Windows 默认 GBK 写出乱码。
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOGGER_NAME = "api-test"
LOG_FORMAT = "%(asctime)s | %(levelname)-5s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def get_logger(name: str = DEFAULT_LOGGER_NAME, log_dir: Path | None = None) -> logging.Logger:
    """返回带文件与终端双输出的 logger；重复调用返回同一实例且不重复挂 handler。"""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    target_dir = Path(log_dir) if log_dir is not None else PROJECT_ROOT / "logs"
    target_dir.mkdir(parents=True, exist_ok=True)
    log_file = target_dir / f"{name}-{time.strftime('%Y%m%d-%H%M%S')}.log"

    logger.setLevel(logging.INFO)
    logger.propagate = False

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger

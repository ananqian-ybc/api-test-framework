"""环境配置加载：default 段提供默认值，环境段只写差异。

配置即代码之外唯一的"环境开关"，集中在这里，用例层不允许出现硬编码地址。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from common.exceptions import SettingsError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR_NAME = "config"
CONFIG_FILE_NAME = "config.yaml"
DEFAULT_ENV = "dev"
DEFAULT_SECTION = "default"
DEFAULTS: dict[str, Any] = {
    "timeout": 10.0,
    "verify_ssl": False,
    "username": "",
    "password": "",
}


@dataclass(frozen=True)
class Settings:
    """一次运行所需的全部配置；frozen 防止用例之间互相污染。"""

    env: str
    base_url: str
    timeout: float
    verify_ssl: bool
    username: str
    password: str


def _read_config_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SettingsError(f"配置文件不存在: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise SettingsError(f"配置文件 YAML 解析失败: {path}\n{exc}") from exc
    if not isinstance(raw, dict):
        raise SettingsError(f"配置文件根节点必须是映射（key: value）: {path}")
    return raw


def _env_section(raw: dict[str, Any], env: str, path: Path) -> dict[str, Any]:
    if env not in raw:
        available = ", ".join(key for key in raw if key != DEFAULT_SECTION) or "无"
        raise SettingsError(f"配置文件中不存在环境 '{env}'，可用环境: {available}（{path}）")
    section = raw[env] or {}
    if not isinstance(section, dict):
        raise SettingsError(f"环境 '{env}' 的配置必须是映射: {path}")
    return section


def load_settings(env: str = DEFAULT_ENV, config_dir: Path | None = None) -> Settings:
    """读取 config.yaml 并把 default 段与指定环境段合并成 Settings。"""
    directory = Path(config_dir) if config_dir is not None else PROJECT_ROOT / CONFIG_DIR_NAME
    path = directory / CONFIG_FILE_NAME
    raw = _read_config_file(path)

    defaults = raw.get(DEFAULT_SECTION) or {}
    if not isinstance(defaults, dict):
        raise SettingsError(f"default 段必须是映射: {path}")
    merged: dict[str, Any] = {**DEFAULTS, **defaults, **_env_section(raw, env, path)}

    base_url = merged.get("base_url")
    if not isinstance(base_url, str) or not base_url.strip():
        raise SettingsError(f"环境 '{env}' 缺少必填配置 base_url: {path}")

    return Settings(
        env=env,
        base_url=base_url.strip().rstrip("/"),
        timeout=float(merged["timeout"]),
        verify_ssl=bool(merged["verify_ssl"]),
        username=str(merged["username"]),
        password=str(merged["password"]),
    )

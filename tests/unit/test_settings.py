"""配置加载的单元测试（不依赖网络）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from common.exceptions import SettingsError
from common.settings import load_settings

CONFIG_YAML = """
default:
  timeout: 15
  verify_ssl: false
  username: tester
  password: Test@123456
dev:
  base_url: http://127.0.0.1:8123
ci:
  base_url: http://sut.internal:8000
"""


def _write_config(tmp_path: Path, content: str = CONFIG_YAML) -> Path:
    config_dir = tmp_path / "config"
    config_dir.mkdir(exist_ok=True)
    (config_dir / "config.yaml").write_text(content, encoding="utf-8")
    return config_dir


def test_should_merge_default_section_with_env_section(tmp_path: Path) -> None:
    settings = load_settings("dev", config_dir=_write_config(tmp_path))

    assert settings.env == "dev"
    assert settings.base_url == "http://127.0.0.1:8123"
    assert settings.timeout == 15
    assert settings.verify_ssl is False
    assert settings.username == "tester"
    assert settings.password == "Test@123456"


def test_should_load_ci_env_with_same_defaults(tmp_path: Path) -> None:
    settings = load_settings("ci", config_dir=_write_config(tmp_path))

    assert settings.base_url == "http://sut.internal:8000"
    assert settings.timeout == 15


def test_should_raise_clear_error_when_env_not_defined(tmp_path: Path) -> None:
    with pytest.raises(SettingsError, match="不存在环境 'staging'"):
        load_settings("staging", config_dir=_write_config(tmp_path))


def test_should_raise_clear_error_when_config_file_missing(tmp_path: Path) -> None:
    with pytest.raises(SettingsError, match="配置文件不存在"):
        load_settings("dev", config_dir=tmp_path)


def test_should_raise_clear_error_when_base_url_missing(tmp_path: Path) -> None:
    config_dir = _write_config(tmp_path, "default:\n  timeout: 10\ndev:\n  username: tester\n")

    with pytest.raises(SettingsError, match="base_url"):
        load_settings("dev", config_dir=config_dir)


def test_should_raise_clear_error_when_yaml_is_malformed(tmp_path: Path) -> None:
    config_dir = _write_config(tmp_path, "default: [unclosed\n")

    with pytest.raises(SettingsError, match="YAML"):
        load_settings("dev", config_dir=config_dir)


def test_settings_should_be_immutable(tmp_path: Path) -> None:
    settings = load_settings("dev", config_dir=_write_config(tmp_path))

    with pytest.raises(Exception):
        settings.base_url = "http://mutated"  # type: ignore[misc]

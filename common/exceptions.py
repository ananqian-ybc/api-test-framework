"""框架异常：按失败领域区分类型，避免所有错误都退化成 Exception。"""

from __future__ import annotations


class ApiTestError(Exception):
    """框架异常基类。"""


class SettingsError(ApiTestError):
    """配置加载失败：文件缺失、环境不存在、必填项缺失。"""


class DataError(ApiTestError):
    """测试数据加载失败：文件缺失、YAML 非法、数据结构不符。"""


class ApiConnectionError(ApiTestError):
    """无法连接被测服务（服务未启动、地址错误）。"""


class ApiTimeoutError(ApiTestError):
    """请求超时。"""


class ApiBusinessError(ApiTestError):
    """接口返回了非预期状态码，属于业务/契约问题（非连接问题）。"""

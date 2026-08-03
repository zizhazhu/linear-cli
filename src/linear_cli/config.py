"""配置文件路径解析、凭据持久化与凭据来源解析。

``.env`` 是 :func:`resolve_api_key` 的显式数据源之一（从用户工作目录向上
查找，只读取、不写入 ``os.environ``），使 ``LINEAR_API_KEY`` 可配置在
项目根目录的 ``.env`` 中。
"""

import os
import tomllib
from pathlib import Path

from dotenv import dotenv_values, find_dotenv

APP_NAME = "linear-cli"
CONFIG_FILENAME = "config.toml"


def get_config_path() -> Path:
    """解析配置文件路径。

    优先级（全平台统一，不做平台分支）：
    1. ``LINEAR_CONFIG_PATH`` 环境变量（直接指向文件）
    2. ``$XDG_CONFIG_HOME/linear-cli/``（设了就认）
    3. ``~/.config/linear-cli/``（最终回落）
    """
    env = os.environ.get("LINEAR_CONFIG_PATH")
    if env:
        return Path(env)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / APP_NAME / CONFIG_FILENAME


def write_api_key_to_config(path: Path, api_key: str) -> None:
    """将 API key 以 TOML 格式写入配置文件，覆盖已有内容。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'api_key = "{api_key}"\n')


def read_api_key_from_config(path: Path) -> str | None:
    """从配置文件读取 API key；文件不存在时返回 ``None``。"""
    if not path.exists():
        return None
    with path.open("rb") as f:
        data = tomllib.load(f)
    return data.get("api_key")


class MissingApiKeyError(RuntimeError):
    """所有凭据来源均未提供 Linear API key 时抛出。"""


def resolve_api_key() -> str:
    """按优先级解析 API key：环境变量 → ``.env`` → 配置文件。

    ``.env`` 经 ``dotenv_values`` 只读解析，不注入 ``os.environ``。
    三者全空时抛 :class:`MissingApiKeyError`。
    """
    if env_key := os.environ.get("LINEAR_API_KEY"):
        return env_key
    if dotenv_key := dotenv_values(find_dotenv(usecwd=True)).get("LINEAR_API_KEY"):
        return dotenv_key
    config_key = read_api_key_from_config(get_config_path())
    if config_key:
        return config_key
    raise MissingApiKeyError(
        "No Linear API key found; set LINEAR_API_KEY (env or .env) "
        "or run `linear login`."
    )

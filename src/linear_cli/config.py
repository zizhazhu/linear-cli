"""配置文件路径解析与凭据持久化。

导入时自动加载 ``.env`` 文件（从用户工作目录向上查找，不覆盖已有的
shell 环境变量），使 ``LINEAR_API_KEY`` 等变量可在项目根目录的 ``.env``
中配置。
"""

import os
import tomllib
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(usecwd=True))

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


def save_api_key(path: Path, api_key: str) -> None:
    """将 API key 以 TOML 格式写入配置文件，覆盖已有内容。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'api_key = "{api_key}"\n')


def load_api_key(path: Path) -> str | None:
    """从配置文件读取 API key；文件不存在时返回 ``None``。"""
    if not path.exists():
        return None
    with path.open("rb") as f:
        data = tomllib.load(f)
    return data.get("api_key")


class MissingApiKeyError(RuntimeError):
    """所有凭据来源均未提供 Linear API key 时抛出。"""


def resolve_api_key(cli_key: str | None) -> str:
    """按优先级解析 API key：CLI 参数 → ``LINEAR_API_KEY`` → 配置文件。

    三者全空时抛 :class:`MissingApiKeyError`。
    """
    if cli_key:
        return cli_key
    env_key = os.environ.get("LINEAR_API_KEY")
    if env_key:
        return env_key
    config_key = load_api_key(get_config_path())
    if config_key:
        return config_key
    raise MissingApiKeyError(
        "No Linear API key found; set LINEAR_API_KEY (env or .env) "
        "or run `linear login`."
    )

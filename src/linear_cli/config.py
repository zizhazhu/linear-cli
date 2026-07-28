"""配置文件路径解析与凭据持久化。"""

import os
import tomllib
from pathlib import Path

import platformdirs

APP_NAME = "linear-cli"
CONFIG_FILENAME = "config.toml"


def get_config_path() -> Path:
    """解析配置文件路径。

    优先级：
    1. ``LINEAR_CONFIG_PATH`` 环境变量（直接指向文件）
    2. 平台默认路径（``$XDG_CONFIG_HOME/linear-cli/`` 或
       ``~/.config/linear-cli/``，由 platformdirs 决定）
    """
    env = os.environ.get("LINEAR_CONFIG_PATH")
    if env:
        return Path(env)
    return platformdirs.user_config_path(APP_NAME) / CONFIG_FILENAME


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

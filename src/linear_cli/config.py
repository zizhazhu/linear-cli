"""配置文件路径解析与凭据持久化。"""

import os
import tomllib
from pathlib import Path

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

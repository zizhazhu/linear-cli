"""真实 API 契约测试的共享设施。

``.env`` 由本模块显式加载（从工作目录向上查找），不依赖被测代码导入时
的副作用；key 在导入时快照，此后 conftest 的环境隔离不影响取值。
"""

import os
from pathlib import Path

import pytest
from dotenv import find_dotenv, load_dotenv

from linear_cli.config import save_api_key

load_dotenv(find_dotenv(usecwd=True))

# 导入时快照：shell 环境变量优先，.env 补缺（load_dotenv 不覆盖已有变量）。
# conftest 的 config_path fixture 会在每个测试前清除 LINEAR_API_KEY，
# 故必须在 fixture 生效前完成取值。
_REAL_API_KEY = os.environ.get("LINEAR_API_KEY")


def require_real_api_key(config_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """取真实 API key，缺失时 skip；返回前把同一把 key 钉进两个凭据来源。

    - ``LINEAR_API_KEY`` 环境变量：恢复被 conftest 隔离掉的值，CLI 按优先级
      走 env 分支；
    - ``config_path`` 配置文件：模拟 login 后的持久化状态。

    CLI 调用与测试内直接调用（如 ``archive_issue``）因此必然使用同一把
    key，「创建用的 key 是环境变量的还是配置文件的」不构成问题。
    """
    if not _REAL_API_KEY:
        pytest.skip("LINEAR_API_KEY 未设置（env 或 .env），跳过真实 API 测试")
    monkeypatch.setenv("LINEAR_API_KEY", _REAL_API_KEY)
    save_api_key(config_path, _REAL_API_KEY)
    return _REAL_API_KEY

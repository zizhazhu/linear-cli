"""真实 API 契约测试的共享设施。

``.env`` 由本模块显式读取（``dotenv_values``，从工作目录向上查找，不写入
``os.environ``），不依赖被测代码导入时的副作用；key 在导入时快照，
此后 conftest 的环境隔离不影响取值。
"""

import os
from pathlib import Path

import httpx
import pytest
from dotenv import dotenv_values, find_dotenv

from linear_cli.config import write_api_key_to_config


def _snapshot_real_api_key() -> str | None:
    """shell 环境变量优先，``.env`` 补缺；只读，不污染环境变量。"""
    if key := os.environ.get("LINEAR_API_KEY"):
        return key
    return dotenv_values(find_dotenv(usecwd=True)).get("LINEAR_API_KEY")


# 导入时快照：conftest 的 config_path fixture 会在每个测试前清除
# LINEAR_API_KEY，故必须在 fixture 生效前完成取值。
_REAL_API_KEY = _snapshot_real_api_key()


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
    write_api_key_to_config(config_path, _REAL_API_KEY)
    return _REAL_API_KEY


def delete_issue_label(api_key: str, label_id: str) -> None:
    """删除 issue 标签（测试清理用；命令面不含标签删除）。

    独立于被测代码直连 GraphQL，避免为清理手段往生产模块塞测试专用函数。
    """
    response = httpx.post(
        "https://api.linear.app/graphql",
        json={
            "query": "mutation($id: String!) { issueLabelDelete(id: $id) { success } }",
            "variables": {"id": label_id},
        },
        headers={"Authorization": api_key},
    )
    response.raise_for_status()


def comment_parent_id(api_key: str, comment_id: str) -> str | None:
    """直查评论的父评论 id（测试读回验证用；CLI 的 list 输出不含 parent 字段）。"""
    response = httpx.post(
        "https://api.linear.app/graphql",
        json={
            "query": "query($id: String!) { comment(id: $id) { parent { id } } }",
            "variables": {"id": comment_id},
        },
        headers={"Authorization": api_key},
    )
    response.raise_for_status()
    body = response.json()
    if body.get("errors"):
        raise AssertionError(f"comment query failed: {body['errors']}")
    parent = body["data"]["comment"]["parent"]
    return parent["id"] if parent else None

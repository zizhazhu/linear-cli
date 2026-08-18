"""结构化 JSON 错误信封。

所有命令的失败输出统一为 stderr 上的单行 JSON：
``{"error": {"type": ..., ...}}``，``type`` 取值 ``auth`` / ``not_found`` /
``graphql`` / ``http``。渲染集中在这一层，命令层只负责把异常分类后交给
对应的 emit 函数。
"""

import json
from typing import NoReturn

import httpx
import typer

from linear_cli.api import GraphQLAPIError

# 账号级 GraphQL 错误的关键词：命中时除 messages 外再附完整原始响应正文
_ACCOUNT_ERROR_KEYWORDS = ("AUTHENTICATION", "AUTHORIZATION", "RATE_LIMIT")


def _emit(error: dict[str, object]) -> NoReturn:
    """把错误信封输出为 stderr 单行 JSON，并以退出码 1 退出。"""
    typer.echo(json.dumps({"error": error}, ensure_ascii=False), err=True)
    raise typer.Exit(1)


def emit_auth_error(message: str) -> NoReturn:
    """凭据缺失等认证错误。"""
    _emit({"type": "auth", "messages": [message]})


def emit_not_found_error(messages: list[str]) -> NoReturn:
    """目标资源不存在（Team、issue 等）。"""
    _emit({"type": "not_found", "messages": messages})


def _is_account_error(errors: list[dict]) -> bool:
    """判断 GraphQL errors 是否属认证/授权/限流等账号级错误。"""
    for err in errors:
        ext = err.get("extensions") or {}
        blob = f"{ext.get('code', '')} {ext.get('type', '')}".upper()
        if any(keyword in blob for keyword in _ACCOUNT_ERROR_KEYWORDS):
            return True
    return False


def emit_api_error(exc: GraphQLAPIError | httpx.HTTPStatusError) -> NoReturn:
    """渲染 Linear API 错误。

    GraphQL ``errors``：``messages`` 逐条为 ``errors[].message`` 原文，不翻译
    不裁剪、保持顺序；账号级错误再附 ``raw``（完整原始响应正文）。HTTP 错误：
    ``status`` 为状态码，``raw`` 为原始响应正文文本。
    """
    if isinstance(exc, GraphQLAPIError):
        error: dict[str, object] = {"type": "graphql", "messages": exc.messages}
        if _is_account_error(exc.errors):
            error["raw"] = exc.raw_body
        _emit(error)
    _emit({"type": "http", "status": exc.response.status_code, "raw": exc.response.text})

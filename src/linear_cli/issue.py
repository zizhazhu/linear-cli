"""``issue`` 命令组：create 与 view。"""

import json
from typing import NoReturn

import httpx
import typer

from linear_cli.api import (
    GraphQLAPIError,
    TeamNotFoundError,
    create_issue,
    fetch_issue,
)
from linear_cli.config import MissingApiKeyError, resolve_api_key

issue_app = typer.Typer(
    name="issue",
    help="操作 Linear issue。",
    no_args_is_help=True,
)

# 账号级 GraphQL 错误的关键词：命中时除 message 原文外再贴原始响应正文
_ACCOUNT_ERROR_KEYWORDS = ("AUTHENTICATION", "AUTHORIZATION", "RATE_LIMIT")


def _load_api_key_or_exit() -> str:
    """按优先级解析 API key（env → 配置文件）；全部落空时提示并以退出码 1 退出。"""
    try:
        return resolve_api_key(None)
    except MissingApiKeyError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from None


def _is_account_error(errors: list[dict]) -> bool:
    """判断 GraphQL errors 是否属认证/授权/限流等账号级错误。"""
    for err in errors:
        ext = err.get("extensions") or {}
        blob = f"{ext.get('code', '')} {ext.get('type', '')}".upper()
        if any(keyword in blob for keyword in _ACCOUNT_ERROR_KEYWORDS):
            return True
    return False


def _handle_api_error(exc: Exception) -> NoReturn:
    """把 Linear API 错误原样输出到 stderr 后以退出码 1 退出。

    GraphQL ``errors``：逐条输出 ``errors[].message`` 原文，不翻译不裁剪；
    账号级错误额外贴原始响应正文。HTTP 错误：贴原始响应正文。
    """
    if isinstance(exc, GraphQLAPIError):
        for message in exc.messages:
            typer.echo(message, err=True)
        if _is_account_error(exc.errors):
            typer.echo(json.dumps(exc.raw_body), err=True)
        raise typer.Exit(1)
    if isinstance(exc, httpx.HTTPStatusError):
        typer.echo(exc.response.text, err=True)
        raise typer.Exit(1)
    raise exc


@issue_app.command("create")
def create(
    team: str = typer.Option(
        ..., "--team", "-t", help="Team 缩写，如 TES。"
    ),
    title: str = typer.Option(..., "--title", help="Issue 标题。"),
    body: str = typer.Option(..., "--body", "-b", help="Issue 正文（Markdown）。"),
    json_output: bool = typer.Option(
        False, "--json", help="以 JSON 输出标识与 URL。"
    ),
) -> None:
    """创建一条 issue 并返回标识与网页 URL。"""
    api_key = _load_api_key_or_exit()
    try:
        issue = create_issue(api_key, team, title, body)
    except TeamNotFoundError as exc:
        typer.echo(f"error: Team 缩写 {exc.key!r} 不存在。", err=True)
        raise typer.Exit(1) from None
    except (GraphQLAPIError, httpx.HTTPStatusError) as exc:
        _handle_api_error(exc)
    else:
        if json_output:
            typer.echo(
                json.dumps({"identifier": issue["identifier"], "url": issue["url"]})
            )
        else:
            typer.echo(f"{issue['identifier']} {issue['url']}")


@issue_app.command("view")
def view(
    issue_id: str = typer.Argument(..., help="Issue 标识，如 TES-123。"),
    json_output: bool = typer.Option(
        False, "--json", help="以 JSON 输出 issue。"
    ),
) -> None:
    """按标识读回一条 issue（无需 Team 参数）。"""
    api_key = _load_api_key_or_exit()
    try:
        issue = fetch_issue(api_key, issue_id)
    except (GraphQLAPIError, httpx.HTTPStatusError) as exc:
        _handle_api_error(exc)
    else:
        if issue is None:
            typer.echo(f"error: issue {issue_id!r} 不存在。", err=True)
            raise typer.Exit(1) from None
        if json_output:
            typer.echo(json.dumps(issue))
        else:
            typer.echo(f"{issue['identifier']} {issue['title']}")
            typer.echo(issue["description"])

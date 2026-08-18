"""``issue`` 命令组：create 与 view。"""

import json

import httpx
import typer

from linear_cli.api import (
    GraphQLAPIError,
    TeamNotFoundError,
    create_issue,
    fetch_issue,
)
from linear_cli.config import MissingApiKeyError, resolve_api_key
from linear_cli.errors import (
    emit_api_error,
    emit_auth_error,
    emit_not_found_error,
)

issue_app = typer.Typer(
    name="issue",
    help="操作 Linear issue。",
    no_args_is_help=True,
)


def _resolve_api_key_or_exit() -> str:
    """按优先级解析 API key（env → .env → 配置文件）；全部落空时以退出码 1 退出。"""
    try:
        return resolve_api_key()
    except MissingApiKeyError as exc:
        emit_auth_error(str(exc))


def _shape_issue(node: dict) -> dict:
    """把 GraphQL issue 节点映射为 view 的输出契约形态。

    labels 拍平为名称数组，creator 映射为 createdBy，parent 映射为 parentId
    （可空字段原样为 null），其余字段按 GraphQL 命名原样输出。
    """
    shaped = dict(node)
    shaped["labels"] = [label["name"] for label in node["labels"]["nodes"]]
    shaped["createdBy"] = node["creator"]
    shaped["parentId"] = node["parent"]["id"] if node["parent"] else None
    del shaped["creator"], shaped["parent"]
    return shaped


@issue_app.command("create")
def create(
    team: str = typer.Option(
        ..., "--team", "-t", help="Team 缩写，如 TES。"
    ),
    title: str = typer.Option(..., "--title", help="Issue 标题。"),
    body: str = typer.Option(..., "--body", "-b", help="Issue 正文（Markdown）。"),
    pretty: bool = typer.Option(
        False, "--pretty", help="以人类可读格式输出，而非默认 JSON。"
    ),
) -> None:
    """创建一条 issue 并返回标识与网页 URL。"""
    api_key = _resolve_api_key_or_exit()
    try:
        issue = create_issue(api_key, team, title, body)
    except TeamNotFoundError as exc:
        emit_not_found_error([f"Team 缩写 {exc.key!r} 不存在。"])
    except (GraphQLAPIError, httpx.HTTPStatusError) as exc:
        emit_api_error(exc)
    else:
        if pretty:
            typer.echo(f"{issue['identifier']} {issue['url']}")
        else:
            typer.echo(
                json.dumps(
                    {"identifier": issue["identifier"], "url": issue["url"]},
                    ensure_ascii=False,
                )
            )


@issue_app.command("view")
def view(
    issue_id: str = typer.Argument(..., help="Issue 标识，如 TES-123。"),
    pretty: bool = typer.Option(
        False, "--pretty", help="以人类可读格式输出，而非默认 JSON。"
    ),
) -> None:
    """按标识读回一条 issue（无需 Team 参数）。"""
    api_key = _resolve_api_key_or_exit()
    try:
        issue = fetch_issue(api_key, issue_id)
    except (GraphQLAPIError, httpx.HTTPStatusError) as exc:
        emit_api_error(exc)
    else:
        if issue is None:
            emit_not_found_error([f"issue {issue_id!r} 不存在。"])
        shaped = _shape_issue(issue)
        if pretty:
            typer.echo(f"{shaped['identifier']} {shaped['title']}")
            typer.echo(shaped["description"])
        else:
            typer.echo(json.dumps(shaped, ensure_ascii=False))

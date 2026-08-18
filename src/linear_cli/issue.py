"""``issue`` 命令组：create、view、list、update 与 comment。"""

import json
from enum import Enum

import httpx
import typer
from rich.console import Console
from rich.table import Table

from linear_cli.api import (
    EntityNotFoundError,
    GraphQLAPIError,
    TeamNotFoundError,
    build_issue_filter,
    create_comment,
    create_issue,
    delete_comment,
    fetch_issue,
    fetch_issue_comments,
    fetch_issues,
    update_issue,
)
from linear_cli.errors import emit_api_error, emit_not_found_error, require_api_key

issue_app = typer.Typer(
    name="issue",
    help="操作 Linear issue。",
    no_args_is_help=True,
)


class IssueOrderBy(str, Enum):
    """``issue list --order-by`` 的合法排序键（与 API 的 PaginationOrderBy 对齐）。"""

    createdAt = "createdAt"
    updatedAt = "updatedAt"


comment_app = typer.Typer(
    name="comment",
    help="操作 issue 评论。",
    no_args_is_help=True,
)
issue_app.add_typer(comment_app)


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
    api_key = require_api_key()
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
    api_key = require_api_key()
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


@issue_app.command("list")
def list_issues(
    team: str = typer.Option(None, "--team", help="Team 缩写、名称或 UUID。"),
    state: str = typer.Option(
        None, "--state", help="状态名称、类型（如 started/backlog）或 UUID。"
    ),
    assignee: str = typer.Option(
        None, "--assignee", help="负责人名称、邮箱、UUID 或 me。"
    ),
    label: str = typer.Option(None, "--label", help="标签名称或 UUID。"),
    project: str = typer.Option(
        None, "--project", help="项目名称、slug 或 UUID。"
    ),
    cycle: str = typer.Option(None, "--cycle", help="Cycle 编号、名称或 UUID。"),
    query: str = typer.Option(None, "--query", help="按关键词搜索标题与正文。"),
    created_at: str = typer.Option(
        None,
        "--created-at",
        help="创建时间下界：ISO-8601 日期或 -P1D 类时长（负前缀值需用 "
        "--created-at=-P1D 形式）。",
    ),
    updated_at: str = typer.Option(
        None,
        "--updated-at",
        help="更新时间下界：ISO-8601 日期或 -P1D 类时长（负前缀值需用 "
        "--updated-at=-P1D 形式）。",
    ),
    limit: int = typer.Option(50, "--limit", help="最多返回的 issue 数。"),
    order_by: IssueOrderBy = typer.Option(
        IssueOrderBy.updatedAt,
        "--order-by",
        help="排序键：updatedAt（默认）或 createdAt。",
    ),
    include_archived: bool = typer.Option(
        False, "--include-archived", help="包含已归档的 issue（默认不含）。"
    ),
    pretty: bool = typer.Option(
        False, "--pretty", help="以人类可读格式输出，而非默认 JSON。"
    ),
) -> None:
    """按过滤条件列出工作区的 issue。"""
    api_key = require_api_key()
    issue_filter = build_issue_filter(
        team=team,
        state=state,
        assignee=assignee,
        label=label,
        project=project,
        cycle=cycle,
        query=query,
        created_at=created_at,
        updated_at=updated_at,
    )
    try:
        issues = fetch_issues(
            api_key,
            limit,
            issue_filter=issue_filter,
            order_by=order_by.value,
            include_archived=include_archived,
        )
    except (GraphQLAPIError, httpx.HTTPStatusError) as exc:
        emit_api_error(exc)
    else:
        if pretty:
            _print_issues_table(issues)
        else:
            typer.echo(json.dumps(issues, ensure_ascii=False))


@issue_app.command("update")
def update(
    issue_id: str = typer.Argument(..., help="Issue 标识，如 TES-123。"),
    title: str = typer.Option(None, "--title", help="新标题。"),
    body: str = typer.Option(
        None, "--body", "-b", help="新正文（Markdown，逐字透传）。"
    ),
    state: str = typer.Option(
        None, "--state", help="目标状态名称、类型（如 started）或 UUID。"
    ),
    priority: int = typer.Option(
        None,
        "--priority",
        min=0,
        max=4,
        help="优先级：0=None，1=Urgent，2=High，3=Medium，4=Low。",
    ),
    assignee: str = typer.Option(
        None, "--assignee", help="负责人名称、邮箱、UUID 或 me。"
    ),
    label: str = typer.Option(
        None, "--label", help="要贴上的标签名称或 UUID（不影响已有标签）。"
    ),
    project: str = typer.Option(None, "--project", help="目标项目名称或 UUID。"),
    cycle: str = typer.Option(
        None, "--cycle", help="目标 Cycle 编号、名称或 UUID。"
    ),
    due_date: str = typer.Option(
        None, "--due-date", help="截止日期（yyyy-mm-dd）。"
    ),
    pretty: bool = typer.Option(
        False, "--pretty", help="以人类可读格式输出，而非默认 JSON。"
    ),
) -> None:
    """更新 issue 的指定字段（未传的字段不动），输出更新后的 issue。"""
    fields = (title, body, state, priority, assignee, label, project, cycle, due_date)
    if all(value is None for value in fields):
        raise typer.BadParameter(
            "至少提供一个要更新的字段 flag（--title/--body/--state 等）。",
            param_hint="--title",
        )
    api_key = require_api_key()
    try:
        updated = update_issue(
            api_key,
            issue_id,
            title=title,
            body=body,
            state=state,
            priority=priority,
            assignee=assignee,
            label=label,
            project=project,
            cycle=cycle,
            due_date=due_date,
        )
    except EntityNotFoundError as exc:
        emit_not_found_error([f"{exc.kind} {exc.value!r} 不存在。"])
    except (GraphQLAPIError, httpx.HTTPStatusError) as exc:
        emit_api_error(exc)
    else:
        if updated is None:
            emit_not_found_error([f"issue {issue_id!r} 不存在。"])
        shaped = _shape_issue(updated)
        if pretty:
            typer.echo(f"{shaped['identifier']} {shaped['title']}")
            typer.echo(shaped['description'])
        else:
            typer.echo(json.dumps(shaped, ensure_ascii=False))


def _print_issues_table(issues: list[dict]) -> None:
    """以 rich 表格渲染 issue 列表（--pretty 专用）。"""
    table = Table(show_header=True, header_style="bold")
    for column in ("标识", "标题", "状态", "优先级", "负责人", "更新时间"):
        table.add_column(column)
    for issue in issues:
        table.add_row(
            issue["identifier"],
            issue["title"],
            issue["state"]["name"],
            str(issue["priority"]),
            issue["assignee"]["name"] if issue["assignee"] else "-",
            issue["updatedAt"],
        )
    Console().print(table)


@comment_app.command("list")
def list_comments(
    issue_id: str = typer.Argument(..., help="Issue 标识，如 TES-123。"),
    pretty: bool = typer.Option(
        False, "--pretty", help="以人类可读格式输出，而非默认 JSON。"
    ),
) -> None:
    """列出 issue 的评论（按创建时间序）。"""
    api_key = require_api_key()
    try:
        comments = fetch_issue_comments(api_key, issue_id)
    except (GraphQLAPIError, httpx.HTTPStatusError) as exc:
        emit_api_error(exc)
    else:
        if comments is None:
            emit_not_found_error([f"issue {issue_id!r} 不存在。"])
        if pretty:
            for comment in comments:
                user = comment["user"]["name"] if comment["user"] else "未知用户"
                typer.echo(f"{comment['createdAt']} {user}")
                typer.echo(comment["body"])
                typer.echo()
        else:
            typer.echo(json.dumps(comments, ensure_ascii=False))


@comment_app.command("add")
def add_comment(
    issue_id: str = typer.Argument(..., help="Issue 标识，如 TES-123。"),
    body: str = typer.Option(..., "--body", "-b", help="评论正文（Markdown）。"),
    pretty: bool = typer.Option(
        False, "--pretty", help="以人类可读格式输出，而非默认 JSON。"
    ),
) -> None:
    """给 issue 添加一条评论（正文逐字透传）。"""
    api_key = require_api_key()
    try:
        comment = create_comment(api_key, issue_id, body)
    except (GraphQLAPIError, httpx.HTTPStatusError) as exc:
        emit_api_error(exc)
    else:
        if comment is None:
            emit_not_found_error([f"issue {issue_id!r} 不存在。"])
        if pretty:
            typer.echo(comment["url"])
        else:
            typer.echo(
                json.dumps(
                    {"id": comment["id"], "url": comment["url"]},
                    ensure_ascii=False,
                )
            )


@comment_app.command("delete")
def delete_comment_command(
    comment_id: str = typer.Argument(
        ..., help="评论 UUID（从 `issue comment list` 获得）。"
    ),
    pretty: bool = typer.Option(
        False, "--pretty", help="以人类可读格式输出，而非默认 JSON。"
    ),
) -> None:
    """按 UUID 删除一条评论。"""
    api_key = require_api_key()
    try:
        deleted = delete_comment(api_key, comment_id)
    except (GraphQLAPIError, httpx.HTTPStatusError) as exc:
        emit_api_error(exc)
    else:
        result = {"id": comment_id, "deleted": deleted}
        if pretty:
            typer.echo(f"deleted {comment_id}")
        else:
            typer.echo(json.dumps(result, ensure_ascii=False))

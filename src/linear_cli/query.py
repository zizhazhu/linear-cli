"""查询层命令组：核心层命令的取值来源（team/user/status/label/project/cycle）。

设计见 docs/command-design.md 查询层一节：各对象一条 list 即可，不做 get；
``label create`` 供 ``issue update --label`` 贴尚不存在的标签。
"""

import json

import httpx
import typer
from rich.console import Console
from rich.table import Table

from linear_cli.api import (
    GraphQLAPIError,
    TeamNotFoundError,
    create_issue_label,
    fetch_issue_labels,
    fetch_projects,
    fetch_team_cycles,
    fetch_team_states,
    fetch_teams,
    fetch_users,
    resolve_team_id,
)
from linear_cli.errors import emit_api_error, emit_not_found_error, require_api_key

team_app = typer.Typer(name="team", help="查询 Team。", no_args_is_help=True)
user_app = typer.Typer(name="user", help="查询用户。", no_args_is_help=True)
status_app = typer.Typer(name="status", help="查询工作流状态。", no_args_is_help=True)
label_app = typer.Typer(name="label", help="查询与创建 issue 标签。", no_args_is_help=True)
project_app = typer.Typer(name="project", help="查询项目。", no_args_is_help=True)
cycle_app = typer.Typer(name="cycle", help="查询 Cycle。", no_args_is_help=True)


def _print_table(columns: tuple[str, ...], rows: list[tuple]) -> None:
    """以 rich 表格渲染查询层列表（--pretty 专用）。"""
    table = Table(show_header=True, header_style="bold")
    for column in columns:
        table.add_column(column)
    for row in rows:
        table.add_row(*(str(cell) if cell is not None else "-" for cell in row))
    Console().print(table)


@team_app.command("list")
def team_list(
    pretty: bool = typer.Option(
        False, "--pretty", help="以人类可读格式输出，而非默认 JSON。"
    ),
) -> None:
    """列出工作区的 Team（id/key/name）。"""
    api_key = require_api_key()
    try:
        teams = fetch_teams(api_key)
    except (GraphQLAPIError, httpx.HTTPStatusError) as exc:
        emit_api_error(exc)
    else:
        if pretty:
            _print_table(
                ("id", "key", "name"), [(t["id"], t["key"], t["name"]) for t in teams]
            )
        else:
            typer.echo(json.dumps(teams, ensure_ascii=False))


@user_app.command("list")
def user_list(
    pretty: bool = typer.Option(
        False, "--pretty", help="以人类可读格式输出，而非默认 JSON。"
    ),
) -> None:
    """列出工作区用户（id/name/displayName/email/active）。"""
    api_key = require_api_key()
    try:
        users = fetch_users(api_key)
    except (GraphQLAPIError, httpx.HTTPStatusError) as exc:
        emit_api_error(exc)
    else:
        if pretty:
            _print_table(
                ("id", "name", "displayName", "email", "active"),
                [
                    (u["id"], u["name"], u["displayName"], u["email"], u["active"])
                    for u in users
                ],
            )
        else:
            typer.echo(json.dumps(users, ensure_ascii=False))


def _fetch_states(api_key: str, team: str | None) -> list[dict]:
    """按 --team 取值拉取状态：指定 team 只查该 team，缺省拼接全部 team。"""
    if team:
        return fetch_team_states(api_key, resolve_team_id(api_key, team))
    return [
        state
        for t in fetch_teams(api_key)
        for state in fetch_team_states(api_key, t["id"])
    ]


@status_app.command("list")
def status_list(
    team: str = typer.Option(
        None, "--team", help="Team 缩写或 UUID；缺省列出全部 team 的状态。"
    ),
    pretty: bool = typer.Option(
        False, "--pretty", help="以人类可读格式输出，而非默认 JSON。"
    ),
) -> None:
    """列出工作流状态（id/name/type/position，按 team 拼接）。"""
    api_key = require_api_key()
    try:
        states = _fetch_states(api_key, team)
    except TeamNotFoundError as exc:
        emit_not_found_error([f"Team 缩写 {exc.key!r} 不存在。"])
    except (GraphQLAPIError, httpx.HTTPStatusError) as exc:
        emit_api_error(exc)
    else:
        if pretty:
            _print_table(
                ("id", "name", "type", "position"),
                [(s["id"], s["name"], s["type"], s["position"]) for s in states],
            )
        else:
            typer.echo(json.dumps(states, ensure_ascii=False))


@label_app.command("list")
def label_list(
    team: str = typer.Option(
        None, "--team", help="Team 缩写或 UUID；输出该 team 可用的标签全集。"
    ),
    pretty: bool = typer.Option(
        False, "--pretty", help="以人类可读格式输出，而非默认 JSON。"
    ),
) -> None:
    """列出 issue 标签（id/name/color）。

    ``--team`` 语义对齐 MCP：workspace 级标签（无归属 team）加上该 team 的
    标签，不含其他 team 的。
    """
    api_key = require_api_key()
    try:
        team_id = resolve_team_id(api_key, team) if team else None
        labels = fetch_issue_labels(api_key)
        if team_id:
            labels = [
                label
                for label in labels
                if label["team"] is None or label["team"]["id"] == team_id
            ]
    except TeamNotFoundError as exc:
        emit_not_found_error([f"Team 缩写 {exc.key!r} 不存在。"])
    except (GraphQLAPIError, httpx.HTTPStatusError) as exc:
        emit_api_error(exc)
    else:
        output = [
            {"id": l["id"], "name": l["name"], "color": l["color"]} for l in labels
        ]
        if pretty:
            _print_table(
                ("id", "name", "color"),
                [(l["id"], l["name"], l["color"]) for l in output],
            )
        else:
            typer.echo(json.dumps(output, ensure_ascii=False))


@label_app.command("create")
def label_create(
    team: str = typer.Option(..., "--team", help="Team 缩写或 UUID。"),
    name: str = typer.Option(..., "--name", help="标签名称。"),
    color: str = typer.Option(None, "--color", help="颜色（如 #EB5757）。"),
    pretty: bool = typer.Option(
        False, "--pretty", help="以人类可读格式输出，而非默认 JSON。"
    ),
) -> None:
    """创建一个 issue 标签，返回 id 与名称。"""
    api_key = require_api_key()
    try:
        label = create_issue_label(api_key, team, name, color)
    except TeamNotFoundError as exc:
        emit_not_found_error([f"Team 缩写 {exc.key!r} 不存在。"])
    except (GraphQLAPIError, httpx.HTTPStatusError) as exc:
        emit_api_error(exc)
    else:
        if pretty:
            typer.echo(f"{label['name']} {label['id']}")
        else:
            typer.echo(json.dumps(label, ensure_ascii=False))


@project_app.command("list")
def project_list(
    pretty: bool = typer.Option(
        False, "--pretty", help="以人类可读格式输出，而非默认 JSON。"
    ),
) -> None:
    """列出工作区项目（id/name/state/url）。"""
    api_key = require_api_key()
    try:
        projects = fetch_projects(api_key)
    except (GraphQLAPIError, httpx.HTTPStatusError) as exc:
        emit_api_error(exc)
    else:
        if pretty:
            _print_table(
                ("id", "name", "state", "url"),
                [(p["id"], p["name"], p["state"], p["url"]) for p in projects],
            )
        else:
            typer.echo(json.dumps(projects, ensure_ascii=False))


def _fetch_cycles(api_key: str, team: str | None) -> list[dict]:
    """按 --team 取值拉取 Cycle：指定 team 只查该 team，缺省拼接全部 team。"""
    if team:
        return fetch_team_cycles(api_key, resolve_team_id(api_key, team))
    return [
        cycle
        for t in fetch_teams(api_key)
        for cycle in fetch_team_cycles(api_key, t["id"])
    ]


@cycle_app.command("list")
def cycle_list(
    team: str = typer.Option(
        None, "--team", help="Team 缩写或 UUID；缺省列出全部 team 的 Cycle。"
    ),
    pretty: bool = typer.Option(
        False, "--pretty", help="以人类可读格式输出，而非默认 JSON。"
    ),
) -> None:
    """列出 Cycle（id/number/name/startsAt/endsAt，按 team 拼接）。"""
    api_key = require_api_key()
    try:
        cycles = _fetch_cycles(api_key, team)
    except TeamNotFoundError as exc:
        emit_not_found_error([f"Team 缩写 {exc.key!r} 不存在。"])
    except (GraphQLAPIError, httpx.HTTPStatusError) as exc:
        emit_api_error(exc)
    else:
        if pretty:
            _print_table(
                ("id", "number", "name", "startsAt", "endsAt"),
                [
                    (c["id"], c["number"], c["name"], c["startsAt"], c["endsAt"])
                    for c in cycles
                ],
            )
        else:
            typer.echo(json.dumps(cycles, ensure_ascii=False))

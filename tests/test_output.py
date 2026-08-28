"""输出层测试：15 条数据输出命令的格式契约（默认 JSON 快照 + YAML 视图）。

JSON 快照为字面量：默认输出逐字节不变是本层唯一不可协商的基线，任何输出
形态的改动都必须在这些字面量的 diff 上显形。因此快照只允许「新增」，
不允许为了让实现通过而「修改」。
"""

import json

import httpx
import pytest
import respx
import yaml
from conftest import (
    CREATE_COMMENT_RESPONSE,
    CREATE_ISSUE_RESPONSE,
    CREATE_LABEL_RESPONSE,
    CYCLES_RESPONSE,
    DELETE_COMMENT_RESPONSE,
    FAKE_API_KEY,
    GRAPHQL_ERROR_RESPONSE,
    GRAPHQL_URL,
    ISSUE,
    ISSUE_COMMENTS_RESPONSE,
    ISSUE_LABELS_RESPONSE,
    ISSUE_RESPONSE,
    ISSUE_UPDATE_RESPONSE,
    ISSUES_RESPONSE,
    PROJECTS_RESPONSE,
    TEAM_STATES_RESPONSE,
    TEAMS_RESPONSE,
    USERS_RESPONSE,
    VIEWER_RESPONSE,
    error_envelope,
)
from typer.testing import CliRunner

from linear_cli import app
from linear_cli.config import write_api_key_to_config
from linear_cli.output import OutputFormat, emit

runner = CliRunner()

# 按操作名前缀分发的 GraphQL 响应全集：一处注册，所有命令共用
RESPONSES = {
    "query Viewer": VIEWER_RESPONSE,
    "query Teams": TEAMS_RESPONSE,
    "mutation IssueCreate": CREATE_ISSUE_RESPONSE,
    "query Issue($id": ISSUE_RESPONSE,
    "mutation IssueUpdate": ISSUE_UPDATE_RESPONSE,
    "query Issues(": ISSUES_RESPONSE,
    "query IssueComments": ISSUE_COMMENTS_RESPONSE,
    "mutation CommentCreate": CREATE_COMMENT_RESPONSE,
    "mutation CommentDelete": DELETE_COMMENT_RESPONSE,
    "query Users": USERS_RESPONSE,
    "query TeamStates": TEAM_STATES_RESPONSE,
    "query IssueLabels": ISSUE_LABELS_RESPONSE,
    "mutation IssueLabelCreate": CREATE_LABEL_RESPONSE,
    "query Projects": PROJECTS_RESPONSE,
    "query Cycles": CYCLES_RESPONSE,
}


def _route_all() -> None:
    """按 query 子串分发 GraphQL 响应；未匹配的查询直接抛错，杜绝真实请求。"""

    def handler(request: httpx.Request) -> httpx.Response:
        query = json.loads(request.content)["query"]
        for needle, payload in RESPONSES.items():
            if needle in query:
                return httpx.Response(200, json=payload)
        raise AssertionError(f"unexpected GraphQL operation: {query!r}")

    respx.post(GRAPHQL_URL).mock(side_effect=handler)


@pytest.fixture
def logged_in(config_path):
    """凭据落在临时配置文件里的「已登录」态。"""
    write_api_key_to_config(config_path, FAKE_API_KEY)
    return config_path


# 15 条数据输出命令 × 默认 JSON 输出的逐字节基线（含结尾换行）
JSON_SNAPSHOTS = [
    pytest.param(
        ["login", "--api-key", FAKE_API_KEY],
        '{"viewer": {"id": "4a2b1f8e-9c3d-4e5f-a6b7-c8d9e0f1a2b3", "name": "Test User", "email": "test@example.com"}, "workspace": {"id": "org-id-1", "name": "Acme", "url": "https://linear.app/acme"}}\n',
        id="login",
    ),
    pytest.param(
        ["issue", "create", "--team", "TES", "--title", "T", "--body", "B"],
        '{"identifier": "TES-123", "url": "https://linear.app/acme/issue/TES-123"}\n',
        id="issue create",
    ),
    pytest.param(
        ["issue", "view", "TES-123"],
        '{"id": "a1b2c3d4-1111-2222-3333-444455556666", "identifier": "TES-123", "title": "Test issue", "description": "Body line 1\\nBody line 2", "url": "https://linear.app/acme/issue/TES-123", "branchName": "test-user/tes-123-test-issue", "state": {"id": "state-id-started", "name": "In Progress", "type": "started"}, "priority": 2, "priorityLabel": "High", "estimate": null, "assignee": {"id": "user-id-1", "name": "Test User"}, "team": {"id": "team-id-tes", "key": "TES", "name": "Test"}, "labels": ["bug", "cli"], "project": null, "createdAt": "2026-08-01T00:00:00.000Z", "updatedAt": "2026-08-02T00:00:00.000Z", "archivedAt": null, "completedAt": null, "startedAt": "2026-08-01T12:00:00.000Z", "canceledAt": null, "dueDate": null, "createdBy": {"id": "user-id-2", "name": "Creator User"}, "parentId": null}\n',
        id="issue view",
    ),
    pytest.param(
        ["issue", "list"],
        '[{"identifier": "TES-123", "title": "Test issue", "url": "https://linear.app/acme/issue/TES-123", "state": {"name": "In Progress", "type": "started"}, "priority": 2, "assignee": {"name": "Test User"}, "updatedAt": "2026-08-02T00:00:00.000Z"}, {"identifier": "TES-124", "title": "No assignee issue", "url": "https://linear.app/acme/issue/TES-124", "state": {"name": "Todo", "type": "unstarted"}, "priority": 0, "assignee": null, "updatedAt": "2026-08-01T00:00:00.000Z"}]\n',
        id="issue list",
    ),
    pytest.param(
        ["issue", "update", "TES-123", "--title", "T"],
        '{"id": "a1b2c3d4-1111-2222-3333-444455556666", "identifier": "TES-123", "title": "Test issue", "description": "Body line 1\\nBody line 2", "url": "https://linear.app/acme/issue/TES-123", "branchName": "test-user/tes-123-test-issue", "state": {"id": "state-id-started", "name": "In Progress", "type": "started"}, "priority": 2, "priorityLabel": "High", "estimate": null, "assignee": {"id": "user-id-1", "name": "Test User"}, "team": {"id": "team-id-tes", "key": "TES", "name": "Test"}, "labels": ["bug", "cli"], "project": null, "createdAt": "2026-08-01T00:00:00.000Z", "updatedAt": "2026-08-02T00:00:00.000Z", "archivedAt": null, "completedAt": null, "startedAt": "2026-08-01T12:00:00.000Z", "canceledAt": null, "dueDate": null, "createdBy": {"id": "user-id-2", "name": "Creator User"}, "parentId": null}\n',
        id="issue update",
    ),
    pytest.param(
        ["issue", "comment", "list", "TES-123"],
        '[{"id": "comment-id-1", "body": "进度汇报", "user": {"id": "user-id-1", "name": "Test User"}, "createdAt": "2026-08-01T10:00:00.000Z", "updatedAt": "2026-08-01T10:00:00.000Z"}]\n',
        id="issue comment list",
    ),
    pytest.param(
        ["issue", "comment", "add", "TES-123", "--body", "B"],
        '{"id": "comment-id-1", "url": "https://linear.app/acme/issue/TES-123#comment-comment-id-1"}\n',
        id="issue comment add",
    ),
    pytest.param(
        ["issue", "comment", "delete", "comment-id-1"],
        '{"id": "comment-id-1", "deleted": true}\n',
        id="issue comment delete",
    ),
    pytest.param(
        ["team", "list"],
        '[{"id": "team-id-tes", "key": "TES", "name": "Test"}]\n',
        id="team list",
    ),
    pytest.param(
        ["user", "list"],
        '[{"id": "user-id-1", "name": "Test User", "displayName": "testuser", "email": "test@example.com", "active": true}, {"id": "user-id-2", "name": "Other User", "displayName": "otheruser", "email": "other@example.com", "active": true}]\n',
        id="user list",
    ),
    pytest.param(
        ["status", "list", "--team", "TES"],
        '[{"id": "state-id-todo", "name": "Todo", "type": "unstarted", "position": 1.0}, {"id": "state-id-started", "name": "In Progress", "type": "started", "position": 2.0}, {"id": "state-id-done", "name": "Done", "type": "completed", "position": 3.0}]\n',
        id="status list",
    ),
    pytest.param(
        ["label", "list", "--team", "TES"],
        '[{"id": "label-id-bug", "name": "Bug", "color": "#EB5757"}, {"id": "label-id-feature", "name": "Feature", "color": "#BB87FC"}, {"id": "label-id-cli", "name": "cli", "color": "#4EA7FC"}]\n',
        id="label list",
    ),
    pytest.param(
        ["label", "create", "--team", "TES", "--name", "cli-new"],
        '{"id": "label-id-new", "name": "cli-new"}\n',
        id="label create",
    ),
    pytest.param(
        ["project", "list"],
        '[{"id": "project-id-1", "name": "dotfiles", "url": "https://linear.app/acme/project/dotfiles-x1y2", "state": "started"}]\n',
        id="project list",
    ),
    pytest.param(
        ["cycle", "list", "--team", "TES"],
        '[{"id": "cycle-id-3", "number": 3, "name": "Cycle 3", "startsAt": "2026-08-10T00:00:00.000Z", "endsAt": "2026-08-16T23:59:59.999Z"}]\n',
        id="cycle list",
    ),
]

# --pretty 移除的覆盖面与快照一致：同一批命令，只换 flag
COMMAND_ARGVS = [pytest.param(case.values[0], id=case.id) for case in JSON_SNAPSHOTS]


@respx.mock
@pytest.mark.parametrize("argv,expected", JSON_SNAPSHOTS)
def test_default_output_is_byte_identical_json(logged_in, argv, expected) -> None:
    """Given 任一数据输出命令与预制的 API 响应
    When 不带任何格式 flag 执行该命令
    Then stdout 与快照基线逐字节相等：单行 JSON、非 ASCII 不转义、字段顺序
    与键名不变
    """
    _route_all()

    result = runner.invoke(app, argv)

    assert result.exit_code == 0, result.stderr
    assert result.stdout == expected


@respx.mock
@pytest.mark.parametrize("argv,expected", JSON_SNAPSHOTS)
def test_yaml_output_is_data_equivalent_to_json(logged_in, argv, expected) -> None:
    """Given 任一数据输出命令与预制的 API 响应
    When 以 -o yaml 执行该命令
    Then stdout 解析为 YAML 后与默认 JSON 输出解析结果相等（同一份归一化
    数据的两个视图，YAML 天然多行）
    """
    _route_all()

    result = runner.invoke(app, [*argv, "-o", "yaml"])

    assert result.exit_code == 0, result.stderr
    assert yaml.safe_load(result.stdout) == json.loads(expected)


@respx.mock
@pytest.mark.parametrize("argv", COMMAND_ARGVS)
def test_pretty_flag_no_longer_accepted(logged_in, argv) -> None:
    """Given --pretty 已从命令面移除
    When 任一数据输出命令仍传 --pretty
    Then typer 报用法错误（退出码 2），且不调用 API
    """
    _route_all()

    result = runner.invoke(app, [*argv, "--pretty"])

    assert result.exit_code == 2
    assert not respx.calls


@respx.mock
def test_yaml_renders_multiline_text_as_a_block_scalar(logged_in) -> None:
    """Given issue 正文是多行 Markdown
    When 以 -o yaml 输出
    Then 正文以 YAML 块标量呈现（逐行原样可读，而非折叠成引号串），且解析
    回来与原文逐字相等
    """
    _route_all()

    result = runner.invoke(app, ["issue", "view", "TES-123", "-o", "yaml"])

    assert result.exit_code == 0, result.stderr
    assert "description: |-\n  Body line 1\n  Body line 2\n" in result.stdout
    assert yaml.safe_load(result.stdout)["description"] == ISSUE["description"]


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("a\nb", id="multiline"),
        pytest.param("a\nb\n", id="trailing newline"),
        pytest.param("a\nb\n\n", id="trailing blank line"),
        pytest.param("trailing space \nnext", id="trailing space"),
        pytest.param("a\r\nb", id="crlf"),
        pytest.param("", id="empty"),
        pytest.param("  leading", id="leading spaces"),
        pytest.param("# 标题\n\n- 列表\n", id="non-ascii markdown"),
    ],
)
def test_yaml_round_trips_awkward_text(capsys, text) -> None:
    """Given 块标量表达不了或易失真的文本（结尾空格、CRLF、空串等）
    When 以 YAML 渲染再解析
    Then 得回逐字相同的文本：块标量只在安全时启用，其余回落到引号串
    """
    emit({"body": text}, OutputFormat.yaml)

    assert yaml.safe_load(capsys.readouterr().out) == {"body": text}


@respx.mock
def test_invalid_output_value_is_a_usage_error(logged_in) -> None:
    """Given -o 只接受 json / yaml
    When 传入非法取值（-o toml）
    Then 走解析层参数错误：退出码 2、stderr 为 usage 文本而非错误信封，
    且不调用 API
    """
    _route_all()

    result = runner.invoke(app, ["team", "list", "-o", "toml"])

    assert result.exit_code == 2
    assert not respx.calls
    assert '"error"' not in result.stderr
    assert "--output" in result.stderr


@respx.mock
@pytest.mark.parametrize("output_flags", [[], ["-o", "json"], ["-o", "yaml"]])
def test_execution_errors_keep_the_envelope_regardless_of_format(
    logged_in, output_flags
) -> None:
    """Given API 返回含 GraphQL errors 的响应
    When 以任一 -o 取值执行命令
    Then 执行层错误契约不受格式影响：退出码 1、stderr 为单行 JSON 错误信封
    """
    respx.post(GRAPHQL_URL).mock(
        return_value=httpx.Response(200, json=GRAPHQL_ERROR_RESPONSE)
    )

    result = runner.invoke(app, ["issue", "view", "TES-123", *output_flags])

    assert result.exit_code == 1
    error = error_envelope(result)
    assert error["type"] == "graphql"
    assert error["messages"] == ["Record not found", "Secondary error message"]

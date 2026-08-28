import json
import uuid

import httpx
import pytest
import respx
from conftest import (
    ACCOUNT_ERROR_RESPONSE,
    COMMENT_NODE,
    CREATE_COMMENT_RESPONSE,
    CREATE_ISSUE_RESPONSE,
    CYCLES_RESPONSE,
    DELETE_COMMENT_RESPONSE,
    EMPTY_ISSUE_COMMENTS_RESPONSE,
    EMPTY_ISSUES_RESPONSE,
    FAKE_API_KEY,
    GRAPHQL_ERROR_RESPONSE,
    GRAPHQL_URL,
    ISSUE,
    ISSUE_COMMENTS_RESPONSE,
    ISSUE_LABELS_RESPONSE,
    ISSUE_LIST,
    ISSUE_RESPONSE,
    ISSUE_UPDATE_RESPONSE,
    ISSUES_RESPONSE,
    NO_ISSUE_COMMENTS_RESPONSE,
    PROJECTS_RESPONSE,
    TEAM_STATES_RESPONSE,
    TEAMS_NO_MATCH_RESPONSE,
    TEAMS_RESPONSE,
    USERS_RESPONSE,
    VIEWER,
    VIEWER_RESPONSE,
    error_envelope,
)
from real_api import comment_parent_id, require_real_api_key
from typer.testing import CliRunner

from linear_cli import app
from linear_cli.api import archive_issue
from linear_cli.config import write_api_key_to_config

runner = CliRunner()


def _route(responses: dict[str, httpx.Response]) -> None:
    """按 query 子串分发 GraphQL 响应；未匹配的查询直接抛错，杜绝真实请求。"""

    def handler(request: httpx.Request) -> httpx.Response:
        query = json.loads(request.content)["query"]
        for needle, response in responses.items():
            if needle in query:
                return response
        raise AssertionError(f"unexpected GraphQL operation: {query!r}")

    respx.post(GRAPHQL_URL).mock(side_effect=handler)


@pytest.mark.parametrize(
    ("args", "missing"),
    [
        (["--title", "T", "--body", "B"], "--team"),
        (["--team", "TES", "--body", "B"], "--title"),
        (["--team", "TES", "--title", "T"], "--body"),
    ],
)
@respx.mock
def test_create_missing_required_param_errors_without_api(
    args: list[str], missing: str, config_path
) -> None:
    # 缺任一必填参数：显式报出缺少的参数、退出码非 0，且不调用 API
    result = runner.invoke(app, ["issue", "create", *args])

    assert result.exit_code == 2
    assert f"Missing option '{missing}'" in result.stderr
    assert not respx.calls


@respx.mock
def test_create_missing_param_precedes_login_check(config_path) -> None:
    # 参数校验先于登录检查：缺参数报用法错误（exit 2），而不是"请先登录"（exit 1）
    result = runner.invoke(app, ["issue", "create", "--title", "T", "--body", "B"])

    assert result.exit_code == 2
    assert "Missing option '--team'" in result.stderr
    assert "linear login" not in result.stderr
    assert not respx.calls


@respx.mock
def test_create_not_logged_in_errors_without_api(config_path) -> None:
    """Given 配置文件不存在（未登录）
    When 执行 issue create
    Then 退出码 1，stderr 输出 type 为 auth 的错误信封，messages 提示先执行
    linear login，且不调用 API
    """
    result = runner.invoke(
        app, ["issue", "create", "--team", "TES", "--title", "T", "--body", "B"]
    )

    assert result.exit_code == 1
    error = error_envelope(result)
    assert error["type"] == "auth"
    assert "linear login" in "; ".join(error["messages"])
    assert not respx.calls


@respx.mock
def test_view_not_logged_in_errors_without_api(config_path) -> None:
    """Given 配置文件不存在（未登录）
    When 执行 issue view
    Then 退出码 1，stderr 输出 type 为 auth 的错误信封，messages 提示先执行
    linear login，且不调用 API
    """
    result = runner.invoke(app, ["issue", "view", "TES-123"])

    assert result.exit_code == 1
    error = error_envelope(result)
    assert error["type"] == "auth"
    assert "linear login" in "; ".join(error["messages"])
    assert not respx.calls


@respx.mock
def test_view_resolves_env_key_without_config_file(config_path, monkeypatch) -> None:
    """Given 配置文件不存在，但 LINEAR_API_KEY 环境变量提供 key
    When view 一个 issue
    Then 请求携带环境变量中的 key，而非报「未登录」
    """
    monkeypatch.setenv("LINEAR_API_KEY", FAKE_API_KEY)
    _route({"query Issue": httpx.Response(200, json=ISSUE_RESPONSE)})

    result = runner.invoke(app, ["issue", "view", "TES-123"])

    assert result.exit_code == 0, result.stderr
    assert respx.calls[0].request.headers["Authorization"] == FAKE_API_KEY


@respx.mock
def test_create_unknown_team_errors_without_issuecreate(config_path) -> None:
    """Given teams 响应里没有缩写 ZZZ
    When 以 --team ZZZ 执行 issue create
    Then 退出码 1，stderr 输出 type 为 not_found 的错误信封，messages 含缩写
    原文 ZZZ，且全程只发 teams 查询、不发 issueCreate
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route({"query Teams": httpx.Response(200, json=TEAMS_NO_MATCH_RESPONSE)})

    result = runner.invoke(
        app, ["issue", "create", "--team", "ZZZ", "--title", "T", "--body", "B"]
    )

    assert result.exit_code == 1
    error = error_envelope(result)
    assert error["type"] == "not_found"
    assert "ZZZ" in "; ".join(error["messages"])
    sent_queries = [
        json.loads(call.request.content)["query"] for call in respx.calls
    ]
    assert len(sent_queries) == 1
    assert "query Teams" in sent_queries[0]


@respx.mock
def test_create_defaults_to_json_output(config_path) -> None:
    """Given 已登录且 team TES 存在
    When 执行 issue create（不带任何输出 flag）
    Then stdout 为单行 JSON：{"identifier": ..., "url": ...}
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route(
        {
            "query Teams": httpx.Response(200, json=TEAMS_RESPONSE),
            "mutation IssueCreate": httpx.Response(200, json=CREATE_ISSUE_RESPONSE),
        }
    )

    result = runner.invoke(
        app, ["issue", "create", "--team", "TES", "--title", "T", "--body", "B"]
    )

    assert result.exit_code == 0, result.stderr
    assert json.loads(result.output) == {
        "identifier": "TES-123",
        "url": ISSUE["url"],
    }


@respx.mock
def test_create_json_flag_removed_errors(config_path) -> None:
    """Given JSON 已成为默认输出
    When 仍传旧的 --json flag
    Then typer 报用法错误（exit 2），不调用 API
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route(
        {
            "query Teams": httpx.Response(200, json=TEAMS_RESPONSE),
            "mutation IssueCreate": httpx.Response(200, json=CREATE_ISSUE_RESPONSE),
        }
    )

    result = runner.invoke(
        app,
        ["issue", "create", "--team", "TES", "--title", "T", "--body", "B", "--json"],
    )

    assert result.exit_code == 2
    assert not respx.calls


@respx.mock
def test_create_passes_body_verbatim_to_api(config_path) -> None:
    # --body 不得被裁剪/改写/规范化：请求变量里的 description 必须与输入严格一致
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route(
        {
            "query Teams": httpx.Response(200, json=TEAMS_RESPONSE),
            "mutation IssueCreate": httpx.Response(200, json=CREATE_ISSUE_RESPONSE),
        }
    )
    body = "line1\n\n- item\n```\n  keep indentation  \n```\nend"

    result = runner.invoke(
        app,
        ["issue", "create", "--team", "TES", "--title", "My title", "--body", body],
    )

    assert result.exit_code == 0, result.stderr
    create_call = next(
        call
        for call in respx.calls
        if "issueCreate" in json.loads(call.request.content)["query"]
    )
    variables = json.loads(create_call.request.content)["variables"]
    assert variables["title"] == "My title"
    assert variables["description"] == body
    # 凭据来自配置文件（conftest 已隔离 LINEAR_API_KEY 环境变量）
    assert create_call.request.headers["Authorization"] == FAKE_API_KEY


@respx.mock
def test_view_defaults_to_full_json_output(config_path) -> None:
    """Given 已登录且目标 issue 存在
    When 执行 issue view（不带任何输出 flag）
    Then stdout 为单行完整 issue JSON：字段 GraphQL 命名，labels 拍平为名称
    数组，creator 映射为 createdBy，parent 映射为 parentId，可空字段原样
    为 null（不省略）
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route({"query Issue": httpx.Response(200, json=ISSUE_RESPONSE)})

    result = runner.invoke(app, ["issue", "view", "TES-123"])

    assert result.exit_code == 0, result.stderr
    assert json.loads(result.output) == ISSUE



@respx.mock
def test_view_json_flag_removed_errors(config_path) -> None:
    """Given JSON 已成为默认输出
    When 仍传旧的 --json flag
    Then typer 报用法错误（exit 2），不调用 API
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route({"query Issue": httpx.Response(200, json=ISSUE_RESPONSE)})

    result = runner.invoke(app, ["issue", "view", "TES-123", "--json"])

    assert result.exit_code == 2
    assert not respx.calls


@respx.mock
def test_list_defaults_to_json_array(config_path) -> None:
    """Given 已登录且工作区有两条 issue（其二无 assignee）
    When 执行 issue list（不带任何 flag）
    Then stdout 为 JSON 数组，逐项为 view 字段集的子集（identifier/title/
    url/state{name,type}/priority/assignee{name}/updatedAt），assignee 为
    null 的项原样保留 null
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route({"query Issues": httpx.Response(200, json=ISSUES_RESPONSE)})

    result = runner.invoke(app, ["issue", "list"])

    assert result.exit_code == 0, result.stderr
    assert json.loads(result.output) == ISSUE_LIST


@respx.mock
def test_list_limit_flag_overrides_default(config_path) -> None:
    """Given 已登录
    When 分别执行 issue list（默认）与 issue list --limit 10
    Then 请求变量 first 默认 50，--limit 时取传入值
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route({"query Issues": httpx.Response(200, json=ISSUES_RESPONSE)})

    default_result = runner.invoke(app, ["issue", "list"])
    limited_result = runner.invoke(app, ["issue", "list", "--limit", "10"])

    assert default_result.exit_code == 0, default_result.stderr
    assert limited_result.exit_code == 0, limited_result.stderr
    firsts = [
        json.loads(call.request.content)["variables"]["first"]
        for call in respx.calls
    ]
    assert firsts == [50, 10]


@respx.mock
def test_list_not_logged_in_errors_without_api(config_path) -> None:
    """Given 配置文件不存在（未登录）
    When 执行 issue list
    Then 退出码 1，stderr 输出 type 为 auth 的错误信封，且不调用 API
    """
    result = runner.invoke(app, ["issue", "list"])

    assert result.exit_code == 1
    error = error_envelope(result)
    assert error["type"] == "auth"
    assert "linear login" in "; ".join(error["messages"])
    assert not respx.calls


@respx.mock
def test_list_empty_result_outputs_empty_array(config_path) -> None:
    """Given 已登录且查询结果为空
    When 执行 issue list
    Then stdout 为空 JSON 数组，退出码 0
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route({"query Issues": httpx.Response(200, json=EMPTY_ISSUES_RESPONSE)})

    result = runner.invoke(app, ["issue", "list"])

    assert result.exit_code == 0, result.stderr
    assert json.loads(result.output) == []


@respx.mock
def test_list_graphql_error_uses_shared_envelope(config_path) -> None:
    """Given Linear 响应含 GraphQL errors
    When 执行 issue list
    Then 退出码 1，stderr 输出与其他命令一致的 graphql 错误信封
    （共享错误通道的接线验证）
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route({"query Issues": httpx.Response(200, json=GRAPHQL_ERROR_RESPONSE)})

    result = runner.invoke(app, ["issue", "list"])

    assert result.exit_code == 1
    error = error_envelope(result)
    assert error["type"] == "graphql"
    assert error["messages"] == ["Record not found", "Secondary error message"]


FILTER_UUID = "11111111-2222-3333-4444-555555555555"


def _last_variables() -> dict:
    """读取最近一次请求的 GraphQL 变量（离线测试断言请求构造用）。"""
    return json.loads(respx.calls[-1].request.content)["variables"]


@pytest.mark.parametrize(
    ("flag_args", "expected_filter"),
    [
        (
            ["--team", "TES"],
            {
                "team": {
                    "or": [
                        {"key": {"eqIgnoreCase": "TES"}},
                        {"name": {"eqIgnoreCase": "TES"}},
                    ]
                }
            },
        ),
        (
            ["--team", FILTER_UUID],
            {
                "team": {
                    "or": [
                        {"id": {"eq": FILTER_UUID}},
                        {"key": {"eqIgnoreCase": FILTER_UUID}},
                        {"name": {"eqIgnoreCase": FILTER_UUID}},
                    ]
                }
            },
        ),
        (
            ["--state", "In Progress"],
            {
                "state": {
                    "or": [
                        {"name": {"eqIgnoreCase": "In Progress"}},
                        {"type": {"eq": "In Progress"}},
                    ]
                }
            },
        ),
        (
            ["--assignee", "me"],
            {"assignee": {"isMe": {"eq": True}}},
        ),
        (
            ["--assignee", "Test User"],
            {"assignee": {"name": {"eqIgnoreCase": "Test User"}}},
        ),
        (
            ["--assignee", "user@example.com"],
            {
                "assignee": {
                    "or": [
                        {"name": {"eqIgnoreCase": "user@example.com"}},
                        {"email": {"eq": "user@example.com"}},
                    ]
                }
            },
        ),
        (
            ["--label", "bug"],
            {"labels": {"some": {"name": {"eqIgnoreCase": "bug"}}}},
        ),
        (
            ["--project", "Website"],
            {
                "project": {
                    "or": [
                        {"name": {"eqIgnoreCase": "Website"}},
                        {"slugId": {"eq": "Website"}},
                    ]
                }
            },
        ),
        (
            ["--cycle", "3"],
            {
                "cycle": {
                    "or": [
                        {"name": {"eqIgnoreCase": "3"}},
                        {"number": {"eq": 3}},
                    ]
                }
            },
        ),
        (
            ["--query", "cli"],
            {
                "or": [
                    {"title": {"containsIgnoreCase": "cli"}},
                    {"description": {"containsIgnoreCase": "cli"}},
                ]
            },
        ),
        (
            ["--created-at=-P1D"],
            {"createdAt": {"gte": "-P1D"}},
        ),
        (
            ["--updated-at", "2026-08-01"],
            {"updatedAt": {"gte": "2026-08-01"}},
        ),
    ],
)
@respx.mock
def test_list_filter_flag_maps_to_graphql_filter(
    config_path, flag_args: list[str], expected_filter: dict
) -> None:
    """Given 已登录
    When issue list 带单个 filter flag
    Then 请求变量的 filter 恰为该 flag 的 GraphQL 等价形态（名称走忽略大小写
    匹配；仅当值形如 UUID 才附 id 分支——服务端 id 比较器校验 UUID 形态）
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route({"query Issues": httpx.Response(200, json=ISSUES_RESPONSE)})

    result = runner.invoke(app, ["issue", "list", *flag_args])

    assert result.exit_code == 0, result.stderr
    assert _last_variables()["filter"] == expected_filter


@respx.mock
def test_list_no_filter_flags_omits_filter_key(config_path) -> None:
    """Given 已登录
    When issue list 不带任何 filter flag
    Then 请求变量不含 filter 键（GraphQL 缺省即无过滤）；orderBy 显式为
    updatedAt（与 MCP 缺省一致），includeArchived 显式为 false（API 缺省
    行为已实测为不含归档，显式传递消除歧义）
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route({"query Issues": httpx.Response(200, json=ISSUES_RESPONSE)})

    result = runner.invoke(app, ["issue", "list"])

    assert result.exit_code == 0, result.stderr
    variables = _last_variables()
    assert "filter" not in variables
    assert variables == {"first": 50, "orderBy": "updatedAt", "includeArchived": False}


@respx.mock
def test_list_combined_filters_are_anded(config_path) -> None:
    """Given 已登录
    When issue list 同时带 --team、--assignee me 与 --query
    Then filter 对象并列三个键（GraphQL 顶层字段为 AND 语义），--query 的
    or 与其他 filter 键共存不互斥
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route({"query Issues": httpx.Response(200, json=ISSUES_RESPONSE)})

    result = runner.invoke(
        app,
        ["issue", "list", "--team", "TES", "--assignee", "me", "--query", "cli"],
    )

    assert result.exit_code == 0, result.stderr
    assert _last_variables()["filter"] == {
        "team": {
            "or": [
                {"key": {"eqIgnoreCase": "TES"}},
                {"name": {"eqIgnoreCase": "TES"}},
            ]
        },
        "assignee": {"isMe": {"eq": True}},
        "or": [
            {"title": {"containsIgnoreCase": "cli"}},
            {"description": {"containsIgnoreCase": "cli"}},
        ],
    }


@respx.mock
def test_list_order_by_defaults_to_updated_at(config_path) -> None:
    """Given 已登录
    When 分别执行 issue list（默认）与 issue list --order-by createdAt
    Then 请求变量 orderBy 分别为 updatedAt（默认，与 MCP 缺省一致）与
    传入值 createdAt
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route({"query Issues": httpx.Response(200, json=ISSUES_RESPONSE)})

    default_result = runner.invoke(app, ["issue", "list"])
    created_result = runner.invoke(app, ["issue", "list", "--order-by", "createdAt"])

    assert default_result.exit_code == 0, default_result.stderr
    assert created_result.exit_code == 0, created_result.stderr
    order_bys = [
        json.loads(call.request.content)["variables"]["orderBy"]
        for call in respx.calls
    ]
    assert order_bys == ["updatedAt", "createdAt"]


@respx.mock
def test_list_include_archived_flag_passes_true(config_path) -> None:
    """Given 已登录
    When 执行 issue list --include-archived
    Then 请求变量 includeArchived 为 true（默认 false，见
    test_list_no_filter_flags_omits_filter_key）
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route({"query Issues": httpx.Response(200, json=ISSUES_RESPONSE)})

    result = runner.invoke(app, ["issue", "list", "--include-archived"])

    assert result.exit_code == 0, result.stderr
    assert _last_variables()["includeArchived"] is True


@respx.mock
def test_list_invalid_order_by_usage_error(config_path) -> None:
    """Given 已登录
    When issue list --order-by priority（非法排序键）
    Then typer 报用法错误（exit 2），不调用 API
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route({"query Issues": httpx.Response(200, json=ISSUES_RESPONSE)})

    result = runner.invoke(app, ["issue", "list", "--order-by", "priority"])

    assert result.exit_code == 2
    assert not respx.calls


@respx.mock
def test_update_requires_at_least_one_field(config_path) -> None:
    """Given 已登录
    When issue update 不带任何字段 flag
    Then 报用法错误（exit 2），不调用 API（部分更新语义要求至少一个字段）
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)

    result = runner.invoke(app, ["issue", "update", "TES-123"])

    assert result.exit_code == 2
    assert not respx.calls


@respx.mock
def test_update_not_logged_in_errors_without_api(config_path) -> None:
    """Given 配置文件不存在（未登录）
    When issue update --title T
    Then 退出码 1，stderr 输出 type 为 auth 的错误信封，且不调用 API
    """
    result = runner.invoke(app, ["issue", "update", "TES-123", "--title", "T"])

    assert result.exit_code == 1
    error = error_envelope(result)
    assert error["type"] == "auth"
    assert "linear login" in "; ".join(error["messages"])
    assert not respx.calls


@respx.mock
def test_update_invalid_priority_usage_error(config_path) -> None:
    """Given 已登录
    When issue update --priority 9（超出 0-4）
    Then 报用法错误（exit 2），不调用 API
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)

    result = runner.invoke(
        app, ["issue", "update", "TES-123", "--priority", "9"]
    )

    assert result.exit_code == 2
    assert not respx.calls


@respx.mock
def test_update_unknown_issue_not_found_before_mutation(config_path) -> None:
    """Given 已登录且标识 TES-999 不存在（issue 节点返回 null）
    When issue update TES-999 --title T
    Then 退出码 1，stderr 输出 type 为 not_found 的错误信封，messages 含标识
    原文，且只发 issue 查询、不发任何解析查询与 mutation
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route({"query Issue(": httpx.Response(200, json={"data": {"issue": None}})})

    result = runner.invoke(app, ["issue", "update", "TES-999", "--title", "T"])

    assert result.exit_code == 1
    error = error_envelope(result)
    assert error["type"] == "not_found"
    assert "TES-999" in "; ".join(error["messages"])
    sent_queries = [
        json.loads(call.request.content)["query"] for call in respx.calls
    ]
    assert len(sent_queries) == 1
    assert sent_queries[0].startswith("query Issue(")


@respx.mock
def test_update_title_body_sends_only_those_fields(config_path) -> None:
    """Given 已登录且目标 issue 存在
    When issue update --title/--body（其余字段不传）
    Then mutation 变量 input 恰只含 title 与 description（部分更新语义：
    未传字段不动），stdout 为 view 字段集的更新后 issue JSON
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route(
        {
            "query Issue(": httpx.Response(200, json=ISSUE_RESPONSE),
            "mutation IssueUpdate(": httpx.Response(200, json=ISSUE_UPDATE_RESPONSE),
        }
    )

    result = runner.invoke(
        app,
        ["issue", "update", "TES-123", "--title", "New title", "--body", "New body"],
    )

    assert result.exit_code == 0, result.stderr
    assert json.loads(result.output) == ISSUE
    mutation_call = next(
        call
        for call in respx.calls
        if json.loads(call.request.content)["query"].startswith(
            "mutation IssueUpdate("
        )
    )
    variables = json.loads(mutation_call.request.content)["variables"]
    assert variables["id"] == ISSUE["id"]
    assert variables["input"] == {"title": "New title", "description": "New body"}


@respx.mock
def test_update_priority_and_due_date_passthrough(config_path) -> None:
    """Given 已登录且目标 issue 存在
    When issue update --priority 2 --due-date 2026-12-31
    Then input 恰为 {priority: 2, dueDate: "2026-12-31"}（数值与日期字符串
    原样透传，不做本地格式化）
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route(
        {
            "query Issue(": httpx.Response(200, json=ISSUE_RESPONSE),
            "mutation IssueUpdate(": httpx.Response(200, json=ISSUE_UPDATE_RESPONSE),
        }
    )

    result = runner.invoke(
        app,
        ["issue", "update", "TES-123", "--priority", "2", "--due-date", "2026-12-31"],
    )

    assert result.exit_code == 0, result.stderr
    variables = _last_variables()
    assert variables["input"] == {"priority": 2, "dueDate": "2026-12-31"}


@respx.mock
def test_update_state_resolves_to_team_state_id(config_path) -> None:
    """Given 已登录且目标 issue 存在，其 team 有状态 In Progress
    When issue update --state "In Progress"
    Then 先查 issue 拿 team id，再查该 team 的 states，input.stateId 为名称
    匹配（忽略大小写）状态的 UUID——写入前客户端解析
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route(
        {
            "query Issue(": httpx.Response(200, json=ISSUE_RESPONSE),
            "query TeamStates(": httpx.Response(200, json=TEAM_STATES_RESPONSE),
            "mutation IssueUpdate(": httpx.Response(200, json=ISSUE_UPDATE_RESPONSE),
        }
    )

    result = runner.invoke(
        app, ["issue", "update", "TES-123", "--state", "in progress"]
    )

    assert result.exit_code == 0, result.stderr
    states_call = next(
        call
        for call in respx.calls
        if json.loads(call.request.content)["query"].startswith(
            "query TeamStates("
        )
    )
    assert (
        json.loads(states_call.request.content)["variables"]
        == {"teamId": ISSUE["team"]["id"]}
    )
    assert _last_variables()["input"] == {"stateId": "state-id-started"}


@respx.mock
def test_update_state_matches_type_when_name_misses(config_path) -> None:
    """Given team 状态无名为 completed 的状态，但有 type 为 completed 的状态
    When issue update --state completed
    Then input.stateId 为按 type 匹配到的状态 UUID
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route(
        {
            "query Issue(": httpx.Response(200, json=ISSUE_RESPONSE),
            "query TeamStates(": httpx.Response(200, json=TEAM_STATES_RESPONSE),
            "mutation IssueUpdate(": httpx.Response(200, json=ISSUE_UPDATE_RESPONSE),
        }
    )

    result = runner.invoke(app, ["issue", "update", "TES-123", "--state", "completed"])

    assert result.exit_code == 0, result.stderr
    assert _last_variables()["input"] == {"stateId": "state-id-done"}


@respx.mock
def test_update_unknown_state_not_found_before_mutation(config_path) -> None:
    """Given team 状态里没有 NoState
    When issue update --state NoState
    Then 退出码 1，stderr 输出 type 为 not_found 的错误信封，messages 含用户
    输入原文 NoState，且只发 issue 与 states 查询、不发 mutation（写入前
    确定性报错）
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route(
        {
            "query Issue(": httpx.Response(200, json=ISSUE_RESPONSE),
            "query TeamStates(": httpx.Response(200, json=TEAM_STATES_RESPONSE),
        }
    )

    result = runner.invoke(app, ["issue", "update", "TES-123", "--state", "NoState"])

    assert result.exit_code == 1
    error = error_envelope(result)
    assert error["type"] == "not_found"
    assert "NoState" in "; ".join(error["messages"])
    sent_queries = [
        json.loads(call.request.content)["query"] for call in respx.calls
    ]
    assert len(sent_queries) == 2
    assert not any(q.startswith("mutation IssueUpdate(") for q in sent_queries)


@respx.mock
@pytest.mark.parametrize(
    "assignee_value", ["Test User", "testuser", "test@example.com"]
)
def test_update_assignee_matches_name_displayname_email(
    config_path, assignee_value: str
) -> None:
    """Given 工作区有用户 Test User（displayName testuser，邮箱 test@example.com）
    When issue update --assignee 分别传名称 / displayName / 邮箱
    Then input.assigneeId 均解析为该用户 UUID（名称类忽略大小写、邮箱精确）
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route(
        {
            "query Issue(": httpx.Response(200, json=ISSUE_RESPONSE),
            "query Users": httpx.Response(200, json=USERS_RESPONSE),
            "mutation IssueUpdate(": httpx.Response(200, json=ISSUE_UPDATE_RESPONSE),
        }
    )

    result = runner.invoke(
        app, ["issue", "update", "TES-123", "--assignee", assignee_value]
    )

    assert result.exit_code == 0, result.stderr
    assert _last_variables()["input"] == {"assigneeId": "user-id-1"}


@respx.mock
def test_update_assignee_me_resolves_viewer(config_path) -> None:
    """Given 当前 viewer 为 Test User
    When issue update --assignee me
    Then 发 viewer 查询，input.assigneeId 为 viewer 的 UUID（不做用户列表匹配）
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route(
        {
            "query Issue(": httpx.Response(200, json=ISSUE_RESPONSE),
            "query Viewer": httpx.Response(200, json=VIEWER_RESPONSE),
            "mutation IssueUpdate(": httpx.Response(200, json=ISSUE_UPDATE_RESPONSE),
        }
    )

    result = runner.invoke(app, ["issue", "update", "TES-123", "--assignee", "me"])

    assert result.exit_code == 0, result.stderr
    assert _last_variables()["input"] == {"assigneeId": VIEWER["id"]}


@respx.mock
def test_update_unknown_assignee_not_found_before_mutation(config_path) -> None:
    """Given 工作区没有名为 Ghost 的用户
    When issue update --assignee Ghost
    Then 退出码 1，not_found 信封含原文 Ghost，不发 mutation
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route(
        {
            "query Issue(": httpx.Response(200, json=ISSUE_RESPONSE),
            "query Users": httpx.Response(200, json=USERS_RESPONSE),
        }
    )

    result = runner.invoke(app, ["issue", "update", "TES-123", "--assignee", "Ghost"])

    assert result.exit_code == 1
    error = error_envelope(result)
    assert error["type"] == "not_found"
    assert "Ghost" in "; ".join(error["messages"])
    assert not any(
        json.loads(call.request.content)["query"].startswith(
            "mutation IssueUpdate("
        )
        for call in respx.calls
    )


@respx.mock
def test_update_label_adds_resolved_label(config_path) -> None:
    """Given 工作区有标签 Bug
    When issue update --label bug
    Then input.addedLabelIds 为解析出的标签 UUID 裸字符串（API 实测只收裸
    UUID，JSON 数组串会被拒）——贴标签语义，已有标签不受影响
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route(
        {
            "query Issue(": httpx.Response(200, json=ISSUE_RESPONSE),
            "query IssueLabels": httpx.Response(200, json=ISSUE_LABELS_RESPONSE),
            "mutation IssueUpdate(": httpx.Response(200, json=ISSUE_UPDATE_RESPONSE),
        }
    )

    result = runner.invoke(app, ["issue", "update", "TES-123", "--label", "bug"])

    assert result.exit_code == 0, result.stderr
    assert _last_variables()["input"] == {"addedLabelIds": "label-id-bug"}


@respx.mock
def test_update_unknown_label_not_found_before_mutation(config_path) -> None:
    """Given 工作区没有名为 NoSuchLabel 的标签
    When issue update --label NoSuchLabel
    Then 退出码 1，not_found 信封含原文，不发 mutation
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route(
        {
            "query Issue(": httpx.Response(200, json=ISSUE_RESPONSE),
            "query IssueLabels": httpx.Response(200, json=ISSUE_LABELS_RESPONSE),
        }
    )

    result = runner.invoke(
        app, ["issue", "update", "TES-123", "--label", "NoSuchLabel"]
    )

    assert result.exit_code == 1
    error = error_envelope(result)
    assert error["type"] == "not_found"
    assert "NoSuchLabel" in "; ".join(error["messages"])
    assert not any(
        json.loads(call.request.content)["query"].startswith(
            "mutation IssueUpdate("
        )
        for call in respx.calls
    )


@respx.mock
def test_update_project_and_cycle_resolve(config_path) -> None:
    """Given 工作区有项目 dotfiles，issue 所属 team 有 Cycle 3
    When issue update --project dotfiles --cycle 3
    Then input.projectId / cycleId 为解析出的 UUID（项目按名称忽略大小写，
    Cycle 先按编号、再按名称）
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route(
        {
            "query Issue(": httpx.Response(200, json=ISSUE_RESPONSE),
            "query Projects": httpx.Response(200, json=PROJECTS_RESPONSE),
            "query Cycles(": httpx.Response(200, json=CYCLES_RESPONSE),
            "mutation IssueUpdate(": httpx.Response(200, json=ISSUE_UPDATE_RESPONSE),
        }
    )

    result = runner.invoke(
        app,
        ["issue", "update", "TES-123", "--project", "DOTFILES", "--cycle", "3"],
    )

    assert result.exit_code == 0, result.stderr
    assert _last_variables()["input"] == {
        "projectId": "project-id-1",
        "cycleId": "cycle-id-3",
    }


@respx.mock
def test_update_graphql_error_uses_shared_envelope(config_path) -> None:
    """Given mutation 响应含 GraphQL errors
    When issue update
    Then 退出码 1，stderr 输出共享的 graphql 错误信封
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route(
        {
            "query Issue(": httpx.Response(200, json=ISSUE_RESPONSE),
            "mutation IssueUpdate(": httpx.Response(200, json=GRAPHQL_ERROR_RESPONSE),
        }
    )

    result = runner.invoke(app, ["issue", "update", "TES-123", "--title", "T"])

    assert result.exit_code == 1
    error = error_envelope(result)
    assert error["type"] == "graphql"
    assert error["messages"] == ["Record not found", "Secondary error message"]


@respx.mock
def test_view_prints_graphql_error_messages_verbatim(config_path) -> None:
    """Given Linear 响应含多条 GraphQL errors
    When 执行 issue view
    Then 退出码 1，stderr 输出 type 为 graphql 的错误信封，messages 逐条为
    errors[].message 原文、保持顺序、不翻译不裁剪，且不附 raw 字段
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route({"query Issue": httpx.Response(200, json=GRAPHQL_ERROR_RESPONSE)})

    result = runner.invoke(app, ["issue", "view", "TES-999"])

    assert result.exit_code == 1
    error = error_envelope(result)
    assert error["type"] == "graphql"
    assert error["messages"] == ["Record not found", "Secondary error message"]
    assert "raw" not in error


@respx.mock
def test_view_account_error_dumps_raw_body(config_path) -> None:
    """Given Linear 返回认证/授权/限流等账号级 GraphQL 错误
    When 执行 issue view
    Then 退出码 1，stderr 输出 type 为 graphql 的错误信封，messages 含 message
    原文，且 raw 字段为完整原始响应正文（含只在 extensions 里的错误码）
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route({"query Issue": httpx.Response(200, json=ACCOUNT_ERROR_RESPONSE)})

    result = runner.invoke(app, ["issue", "view", "TES-999"])

    assert result.exit_code == 1
    error = error_envelope(result)
    assert error["type"] == "graphql"
    assert "Authentication required, not authenticated" in error["messages"]
    assert error["raw"] == ACCOUNT_ERROR_RESPONSE


@respx.mock
def test_view_http_error_prints_raw_body(config_path) -> None:
    """Given Linear 返回 HTTP 非 2xx（如限流 429）
    When 执行 issue view
    Then 退出码 1，stderr 输出 type 为 http 的错误信封，status 为 HTTP 状态码，
    raw 字段为原始响应正文文本
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route(
        {
            "query Issue": httpx.Response(
                429, json={"errors": [{"message": "Rate limit exceeded"}]}
            )
        }
    )

    result = runner.invoke(app, ["issue", "view", "TES-123"])

    assert result.exit_code == 1
    error = error_envelope(result)
    assert error["type"] == "http"
    assert error["status"] == 429
    assert "Rate limit exceeded" in error["raw"]


def test_create_view_roundtrip_real_api(config_path, monkeypatch) -> None:
    """Given 真实 API key 与一段含换行/Markdown/保留空白的正文
    When create 一条带 run 标识的 issue，并立即用返回标识 view 读回（默认 JSON）
    Then 标题与正文逐字一致；读回满足 view 输出契约（identifier 一致、
    state/priority/team/labels/时间戳字段格式正确）；全部断言通过后归档
    （失败则保留现场不归档）
    """
    api_key = require_real_api_key(config_path, monkeypatch)
    run_id = uuid.uuid4().hex[:8]
    title = f"cli-roundtrip-{run_id}"
    # 注意：无序列表用 `* ` 而非 `- `——Linear 服务端会把 `- ` 规范化为 `* `，
    # 其余 Markdown（标题/加粗/引用）与 fenced code block 内空白均逐字保留。
    body = (
        "首行\n"
        "\n"
        "* 列表项一\n"
        "* 列表项二\n"
        "\n"
        "```python\n"
        "def f():\n"
        '    return "  保留空白  "\n'
        "```\n"
        "\n"
        "末行"
    )

    create_result = runner.invoke(
        app,
        ["issue", "create", "--team", "TES", "--title", title, "--body", body],
    )
    assert create_result.exit_code == 0, create_result.stderr
    created = json.loads(create_result.output)
    identifier = created["identifier"]

    try:
        assert identifier.startswith("TES-")
        assert created["url"].startswith("https://linear.app/")
        assert identifier in created["url"]

        view_result = runner.invoke(app, ["issue", "view", identifier])
        assert view_result.exit_code == 0, view_result.stderr
        read_back = json.loads(view_result.output)
        issue_uuid = read_back["id"]
        assert read_back["title"] == title
        assert read_back["description"] == body
        # view 输出契约：字段格式（值因 issue 而异，只断言结构）
        assert read_back["identifier"] == identifier
        assert isinstance(read_back["state"]["name"], str)
        assert isinstance(read_back["state"]["type"], str)
        assert isinstance(read_back["priority"], int)
        assert isinstance(read_back["priorityLabel"], str)
        assert read_back["team"]["key"] == "TES"
        assert isinstance(read_back["labels"], list)
        assert "assignee" in read_back  # 可空，原样为 null
        assert read_back["createdAt"].endswith("Z")
    except Exception:
        # 断言失败保留现场，不归档
        raise

    # 全部断言通过后才归档（可逆，URL 仍可人工查证）；issueArchive 接收 UUID 而非标识
    archive_issue(api_key, issue_uuid)


def test_view_nonexistent_identifier_real_api(config_path, monkeypatch) -> None:
    """Given 真实 API key 与一个格式合法但不存在的标识
    When view 该标识
    Then 退出码非 0，stderr 输出 type 为 graphql 的错误信封，messages 含 Linear
    返回的 errors[].message 原文（Entity not found: Issue ...）
    """
    require_real_api_key(config_path, monkeypatch)

    result = runner.invoke(app, ["issue", "view", "TES-999999"])

    assert result.exit_code != 0
    error = error_envelope(result)
    assert error["type"] == "graphql"
    assert any("Entity not found: Issue" in m for m in error["messages"])


def test_list_real_api(config_path, monkeypatch) -> None:
    """Given 真实 API key
    When issue list --limit 1（不带任何 filter）
    Then 返回恰好 1 条，列表项符合输出契约（identifier 含连字符、url 为
    linear.app 链接、state.name/type 与 priority/updatedAt 格式正确、
    assignee 字段存在且可空）
    """
    require_real_api_key(config_path, monkeypatch)

    result = runner.invoke(app, ["issue", "list", "--limit", "1"])

    assert result.exit_code == 0, result.stderr
    items = json.loads(result.output)
    assert len(items) == 1
    item = items[0]
    assert isinstance(item["identifier"], str) and "-" in item["identifier"]
    assert item["url"].startswith("https://linear.app/")
    assert isinstance(item["state"]["name"], str)
    assert isinstance(item["state"]["type"], str)
    assert isinstance(item["priority"], int)
    assert "assignee" in item  # 可空，原样为 null
    assert item["updatedAt"].endswith("Z")


def test_list_filters_roundtrip_real_api(config_path, monkeypatch) -> None:
    """Given 真实 API key 与一条新建 issue（唯一 run 标识标题，初始状态 Backlog）
    When issue list --team TES --state Backlog --query <run> --created-at=-P1D
         --updated-at=-P1D --order-by updatedAt
    Then 结果恰含该新建 issue（team/state/query/日期过滤服务端读回一致），
    且每一项的 state.name 均为 Backlog；断言通过后归档（失败保留现场）
    """
    api_key = require_real_api_key(config_path, monkeypatch)
    run_id = uuid.uuid4().hex[:8]
    title = f"cli-roundtrip-{run_id}"

    create_result = runner.invoke(
        app, ["issue", "create", "--team", "TES", "--title", title, "--body", "x"]
    )
    assert create_result.exit_code == 0, create_result.stderr
    created = json.loads(create_result.output)

    try:
        result = runner.invoke(
            app,
            [
                "issue", "list",
                "--team", "TES",
                "--state", "Backlog",
                "--query", run_id,
                "--created-at=-P1D",
                "--updated-at=-P1D",
                "--order-by", "updatedAt",
            ],
        )
        assert result.exit_code == 0, result.stderr
        items = json.loads(result.output)
        identifiers = [item["identifier"] for item in items]
        assert identifiers == [created["identifier"]]
        assert all(item["state"]["name"] == "Backlog" for item in items)
    except Exception:
        # 断言失败保留现场，不归档
        raise

    view_result = runner.invoke(app, ["issue", "view", created["identifier"]])
    assert view_result.exit_code == 0, view_result.stderr
    archive_issue(api_key, json.loads(view_result.output)["id"])


def test_update_roundtrip_real_api(config_path, monkeypatch) -> None:
    """Given 真实 API key 与一条新建 issue
    When update --title/--body/--state Todo/--priority/--label bug/--due-date/
         --assignee me，随后 view 读回
    Then 更新输出与读回满足 view 契约且逐字一致（title/body 逐字、
    state.name/priority/labels/dueDate/assignee 读回一致，名称解析忽略
    大小写：bug → Bug）；断言通过后归档（失败保留现场）
    """
    api_key = require_real_api_key(config_path, monkeypatch)
    run_id = uuid.uuid4().hex[:8]
    create_result = runner.invoke(
        app,
        ["issue", "create", "--team", "TES", "--title", f"cli-roundtrip-{run_id}", "--body", "x"],
    )
    assert create_result.exit_code == 0, create_result.stderr
    created = json.loads(create_result.output)
    new_title = f"updated-{run_id}"
    # 不以换行结尾：Linear 服务端会规范化描述的尾部空白（见 create roundtrip）
    new_body = "更新正文\n\n* 列表项"

    try:
        update_result = runner.invoke(
            app,
            [
                "issue", "update", created["identifier"],
                "--title", new_title,
                "--body", new_body,
                "--state", "todo",
                "--priority", "2",
                "--label", "bug",
                "--due-date", "2026-12-31",
                "--assignee", "me",
            ],
        )
        assert update_result.exit_code == 0, update_result.stderr
        updated = json.loads(update_result.output)
        assert updated["identifier"] == created["identifier"]
        assert updated["title"] == new_title
        assert updated["description"] == new_body
        assert updated["state"]["name"] == "Todo"
        assert updated["priority"] == 2
        assert updated["labels"] == ["Bug"]
        assert updated["dueDate"] == "2026-12-31"
        assert updated["assignee"]["name"]

        view_result = runner.invoke(app, ["issue", "view", created["identifier"]])
        assert view_result.exit_code == 0, view_result.stderr
        read_back = json.loads(view_result.output)
        assert read_back["title"] == new_title
        assert read_back["description"] == new_body
        assert read_back["state"]["name"] == "Todo"
        assert read_back["priority"] == 2
        assert read_back["labels"] == ["Bug"]
        assert read_back["dueDate"] == "2026-12-31"
        assert read_back["assignee"]["id"]
    except Exception:
        # 断言失败保留现场，不归档
        raise

    archive_issue(api_key, updated["id"])


# ---------------------------------------------------------------- comment


@respx.mock
def test_comment_list_not_logged_in_errors_without_api(config_path) -> None:
    """Given 配置文件不存在（未登录）
    When 执行 issue comment list
    Then 退出码 1，stderr 输出 type 为 auth 的错误信封，且不调用 API
    """
    result = runner.invoke(app, ["issue", "comment", "list", "TES-123"])

    assert result.exit_code == 1
    error = error_envelope(result)
    assert error["type"] == "auth"
    assert "linear login" in "; ".join(error["messages"])
    assert not respx.calls


@respx.mock
def test_comment_list_outputs_comment_array(config_path) -> None:
    """Given 已登录且 issue 有一条评论
    When 执行 issue comment list TES-123
    Then stdout 为 JSON 数组，逐项为 id/body/user{id,name}/createdAt/
    updatedAt（按创建时间序，由服务端 orderBy 保证）
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route(
        {"query IssueComments(": httpx.Response(200, json=ISSUE_COMMENTS_RESPONSE)}
    )

    result = runner.invoke(app, ["issue", "comment", "list", "TES-123"])

    assert result.exit_code == 0, result.stderr
    assert json.loads(result.output) == [COMMENT_NODE]


@respx.mock
def test_comment_list_empty_outputs_empty_array(config_path) -> None:
    """Given 已登录且 issue 无评论
    When 执行 issue comment list
    Then stdout 为空 JSON 数组，退出码 0
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route(
        {
            "query IssueComments(": httpx.Response(
                200, json=EMPTY_ISSUE_COMMENTS_RESPONSE
            )
        }
    )

    result = runner.invoke(app, ["issue", "comment", "list", "TES-123"])

    assert result.exit_code == 0, result.stderr
    assert json.loads(result.output) == []


@respx.mock
def test_comment_list_unknown_issue_not_found(config_path) -> None:
    """Given 标识 TES-999 不存在（issue 节点返回 null）
    When 执行 issue comment list TES-999
    Then 退出码 1，stderr 输出 type 为 not_found 的错误信封，messages 含标识
    原文
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route(
        {"query IssueComments(": httpx.Response(200, json=NO_ISSUE_COMMENTS_RESPONSE)}
    )

    result = runner.invoke(app, ["issue", "comment", "list", "TES-999"])

    assert result.exit_code == 1
    error = error_envelope(result)
    assert error["type"] == "not_found"
    assert "TES-999" in "; ".join(error["messages"])


@respx.mock
def test_comment_add_outputs_id_and_url(config_path) -> None:
    """Given 已登录且目标 issue 存在
    When 执行 issue comment add TES-123 --body
    Then stdout 为单行 JSON {"id": ..., "url": ...}；mutation input 的
    issueId 为先解析出的 issue UUID、body 逐字透传
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route(
        {
            "query Issue(": httpx.Response(200, json=ISSUE_RESPONSE),
            "mutation CommentCreate(": httpx.Response(
                200, json=CREATE_COMMENT_RESPONSE
            ),
        }
    )

    result = runner.invoke(
        app, ["issue", "comment", "add", "TES-123", "--body", "进度汇报"]
    )

    assert result.exit_code == 0, result.stderr
    assert json.loads(result.output) == {
        "id": "comment-id-1",
        "url": "https://linear.app/acme/issue/TES-123#comment-comment-id-1",
    }
    variables = _last_variables()
    assert variables["input"] == {"issueId": ISSUE["id"], "body": "进度汇报"}


@respx.mock
def test_comment_add_body_verbatim(config_path) -> None:
    """Given 已登录且目标 issue 存在
    When --body 含换行/Markdown/保留空白
    Then mutation input 的 body 与输入严格一致（不裁剪/改写/规范化）
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route(
        {
            "query Issue(": httpx.Response(200, json=ISSUE_RESPONSE),
            "mutation CommentCreate(": httpx.Response(
                200, json=CREATE_COMMENT_RESPONSE
            ),
        }
    )
    body = "line1\n\n- item\n```\n  keep indentation  \n```\nend"

    result = runner.invoke(
        app, ["issue", "comment", "add", "TES-123", "--body", body]
    )

    assert result.exit_code == 0, result.stderr
    assert _last_variables()["input"]["body"] == body


@respx.mock
def test_comment_add_unknown_issue_not_found_before_mutation(config_path) -> None:
    """Given 标识不存在
    When 执行 issue comment add
    Then 退出码 1，not_found 信封含标识原文，且不发 mutation
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route({"query Issue(": httpx.Response(200, json={"data": {"issue": None}})})

    result = runner.invoke(
        app, ["issue", "comment", "add", "TES-999", "--body", "x"]
    )

    assert result.exit_code == 1
    error = error_envelope(result)
    assert error["type"] == "not_found"
    assert "TES-999" in "; ".join(error["messages"])
    assert not any(
        "commentCreate" in json.loads(call.request.content)["query"]
        for call in respx.calls
    )


@respx.mock
def test_comment_delete_outputs_id_and_deleted(config_path) -> None:
    """Given 已登录
    When 执行 issue comment delete <uuid>
    Then stdout 为 {"id": <uuid>, "deleted": true}，mutation 变量 id 为该 UUID
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route(
        {"mutation CommentDelete(": httpx.Response(200, json=DELETE_COMMENT_RESPONSE)}
    )

    result = runner.invoke(app, ["issue", "comment", "delete", "comment-id-1"])

    assert result.exit_code == 0, result.stderr
    assert json.loads(result.output) == {"id": "comment-id-1", "deleted": True}
    assert _last_variables() == {"id": "comment-id-1"}


@respx.mock
def test_comment_delete_nonexistent_graphql_envelope(config_path) -> None:
    """Given 评论 UUID 不存在（服务端 200 + errors）
    When 执行 issue comment delete
    Then 退出码 1，stderr 输出 type 为 graphql 的共享错误信封
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route(
        {"mutation CommentDelete(": httpx.Response(200, json=GRAPHQL_ERROR_RESPONSE)}
    )

    result = runner.invoke(app, ["issue", "comment", "delete", "no-such-id"])

    assert result.exit_code == 1
    error = error_envelope(result)
    assert error["type"] == "graphql"
    assert error["messages"] == ["Record not found", "Secondary error message"]


def test_comment_roundtrip_real_api(config_path, monkeypatch) -> None:
    """Given 真实 API key、一条新建 issue 与一段含换行的评论正文
    When comment add → comment list → comment delete → comment list
    Then add 输出 {id, url}（url 含 issue 路径）；list 读回恰含该评论且 body
    逐字一致、user/createdAt 字段格式正确；delete 后 list 为空；最后归档
    issue（失败保留现场）
    """
    api_key = require_real_api_key(config_path, monkeypatch)
    run_id = uuid.uuid4().hex[:8]
    create_result = runner.invoke(
        app,
        ["issue", "create", "--team", "TES", "--title", f"cli-roundtrip-{run_id}", "--body", "x"],
    )
    assert create_result.exit_code == 0, create_result.stderr
    created = json.loads(create_result.output)
    body = "第一行\n\n* 进度 50%"

    try:
        add_result = runner.invoke(
            app, ["issue", "comment", "add", created["identifier"], "--body", body]
        )
        assert add_result.exit_code == 0, add_result.stderr
        comment = json.loads(add_result.output)
        assert comment["id"]
        assert created["identifier"] in comment["url"]

        list_result = runner.invoke(
            app, ["issue", "comment", "list", created["identifier"]]
        )
        assert list_result.exit_code == 0, list_result.stderr
        comments = json.loads(list_result.output)
        assert len(comments) == 1
        assert comments[0]["id"] == comment["id"]
        assert comments[0]["body"] == body
        assert comments[0]["user"]["name"]
        assert comments[0]["createdAt"].endswith("Z")

        delete_result = runner.invoke(
            app, ["issue", "comment", "delete", comment["id"]]
        )
        assert delete_result.exit_code == 0, delete_result.stderr
        assert json.loads(delete_result.output) == {
            "id": comment["id"],
            "deleted": True,
        }

        list_result = runner.invoke(
            app, ["issue", "comment", "list", created["identifier"]]
        )
        assert list_result.exit_code == 0, list_result.stderr
        assert json.loads(list_result.output) == []
    except Exception:
        # 断言失败保留现场，不归档
        raise

    view_result = runner.invoke(app, ["issue", "view", created["identifier"]])
    assert view_result.exit_code == 0, view_result.stderr
    archive_issue(api_key, json.loads(view_result.output)["id"])


def test_comment_delete_nonexistent_real_api(config_path, monkeypatch) -> None:
    """Given 真实 API key 与一个格式合法但不存在的评论 UUID
    When 执行 issue comment delete
    Then 退出码非 0，stderr 输出 type 为 graphql 的错误信封，messages 含
    Linear 返回的 errors[].message 原文（Entity not found: Comment）
    """
    require_real_api_key(config_path, monkeypatch)

    result = runner.invoke(
        app,
        ["issue", "comment", "delete", "00000000-0000-4000-8000-000000000000"],
    )

    assert result.exit_code != 0
    error = error_envelope(result)
    assert error["type"] == "graphql"
    assert any("Comment" in m for m in error["messages"])


@respx.mock
def test_comment_add_parent_maps_to_parent_id_with_issue_id(config_path) -> None:
    """Given 已登录且目标 issue 存在
    When issue comment add --parent <评论 UUID> --body
    Then mutation input 为 {issueId: 解析出的 UUID, parentId: 传入 UUID, body}
    ——GraphQL 真值：parentId 不能脱离 issueId 单独成立（实测 parentId-only
    被拒，与 MCP 的「回复无需实体引用」描述相反）；输出契约不变
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route(
        {
            "query Issue(": httpx.Response(200, json=ISSUE_RESPONSE),
            "mutation CommentCreate(": httpx.Response(
                200, json=CREATE_COMMENT_RESPONSE
            ),
        }
    )

    result = runner.invoke(
        app,
        [
            "issue", "comment", "add", "TES-123",
            "--parent", "parent-comment-id",
            "--body", "回复内容",
        ],
    )

    assert result.exit_code == 0, result.stderr
    assert json.loads(result.output) == {
        "id": "comment-id-1",
        "url": "https://linear.app/acme/issue/TES-123#comment-comment-id-1",
    }
    assert _last_variables()["input"] == {
        "issueId": ISSUE["id"],
        "parentId": "parent-comment-id",
        "body": "回复内容",
    }


def test_comment_reply_roundtrip_real_api(config_path, monkeypatch) -> None:
    """Given 真实 API key、一条新建 issue 与其下的一条父评论
    When comment add --parent <父评论 UUID>，随后直查 GraphQL 读回
    Then 回复挂到父评论之下（parent.id 读回一致）、父评论的 parent 为 null
    （顶层）；CLI comment list 平铺可见两条；断言通过后删子、删父、归档
    issue（失败保留现场）
    """
    api_key = require_real_api_key(config_path, monkeypatch)
    run_id = uuid.uuid4().hex[:8]
    create_result = runner.invoke(
        app,
        [
            "issue", "create",
            "--team", "TES", "--title", f"cli-roundtrip-{run_id}", "--body", "x",
        ],
    )
    assert create_result.exit_code == 0, create_result.stderr
    created = json.loads(create_result.output)
    identifier = created["identifier"]

    try:
        parent_result = runner.invoke(
            app, ["issue", "comment", "add", identifier, "--body", "父评论"]
        )
        assert parent_result.exit_code == 0, parent_result.stderr
        parent = json.loads(parent_result.output)

        reply_result = runner.invoke(
            app,
            [
                "issue", "comment", "add", identifier,
                "--parent", parent["id"],
                "--body", "子回复",
            ],
        )
        assert reply_result.exit_code == 0, reply_result.stderr
        reply = json.loads(reply_result.output)

        assert comment_parent_id(api_key, reply["id"]) == parent["id"]
        assert comment_parent_id(api_key, parent["id"]) is None

        list_result = runner.invoke(app, ["issue", "comment", "list", identifier])
        assert list_result.exit_code == 0, list_result.stderr
        comments = json.loads(list_result.output)
        assert {c["id"] for c in comments} == {parent["id"], reply["id"]}
        reply_body = next(c["body"] for c in comments if c["id"] == reply["id"])
        assert reply_body == "子回复"
    except Exception:
        # 断言失败保留现场，不清理
        raise

    for comment_id in (reply["id"], parent["id"]):
        delete_result = runner.invoke(
            app, ["issue", "comment", "delete", comment_id]
        )
        assert delete_result.exit_code == 0, delete_result.stderr
    view_result = runner.invoke(app, ["issue", "view", identifier])
    assert view_result.exit_code == 0, view_result.stderr
    archive_issue(api_key, json.loads(view_result.output)["id"])

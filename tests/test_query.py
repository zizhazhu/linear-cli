"""查询层命令（team/user/status/label/project/cycle）测试。

离线测试用 respx 打 HTTP 边界断言请求构造与输出契约；真实 API 测试每条
命令恰一条字段契约（读回格式），`label create` 一条写读回 round-trip。
"""

import json
import uuid

import httpx
import pytest
import respx
from conftest import (
    CREATE_LABEL_RESPONSE,
    CYCLES_RESPONSE,
    FAKE_API_KEY,
    GRAPHQL_ERROR_RESPONSE,
    GRAPHQL_URL,
    ISSUE_LABELS_RESPONSE,
    PROJECTS_RESPONSE,
    TEAM_STATES_RESPONSE,
    TEAMS_NO_MATCH_RESPONSE,
    TEAMS_RESPONSE,
    USERS_RESPONSE,
    error_envelope,
)
from real_api import delete_issue_label, require_real_api_key
from typer.testing import CliRunner

from linear_cli import app
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


def _sent_queries() -> list[str]:
    return [json.loads(call.request.content)["query"] for call in respx.calls]


# ---------------------------------------------------------------- team list


@respx.mock
def test_team_list_outputs_teams(config_path) -> None:
    """Given 已登录且工作区有一个 Team
    When 执行 team list
    Then stdout 为 JSON 数组，逐项为 id/key/name（key 必含——MCP 视图缺此
    字段，以 GraphQL 为准）
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route({"query Teams": httpx.Response(200, json=TEAMS_RESPONSE)})

    result = runner.invoke(app, ["team", "list", "--format", "json"])

    assert result.exit_code == 0, result.stderr
    assert json.loads(result.output) == [{"id": "team-id-tes", "key": "TES", "name": "Test"}]


@respx.mock
def test_team_list_not_logged_in_errors_without_api(config_path) -> None:
    """Given 配置文件不存在（未登录）
    When 执行 team list
    Then 退出码 1，stderr 输出 type 为 auth 的错误信封，且不调用 API
    """
    result = runner.invoke(app, ["team", "list"])

    assert result.exit_code == 1
    error = error_envelope(result)
    assert error["type"] == "auth"
    assert "linear login" in "; ".join(error["messages"])
    assert not respx.calls


@respx.mock
def test_query_commands_share_graphql_error_envelope(config_path) -> None:
    """Given 查询层任一命令（team list）收到含 GraphQL errors 的响应
    When 执行该命令
    Then 退出码 1，stderr 输出与其他命令一致的 graphql 错误信封（查询层
    接线验证，代表性一条）
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route({"query Teams": httpx.Response(200, json=GRAPHQL_ERROR_RESPONSE)})

    result = runner.invoke(app, ["team", "list"])

    assert result.exit_code == 1
    error = error_envelope(result)
    assert error["type"] == "graphql"
    assert error["messages"] == ["Record not found", "Secondary error message"]


# ---------------------------------------------------------------- user list


@respx.mock
def test_user_list_outputs_users(config_path) -> None:
    """Given 已登录且工作区有两位用户
    When 执行 user list
    Then stdout 为 JSON 数组，逐项为 id/name/displayName/email/active
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route({"query Users": httpx.Response(200, json=USERS_RESPONSE)})

    result = runner.invoke(app, ["user", "list", "--format", "json"])

    assert result.exit_code == 0, result.stderr
    assert json.loads(result.output) == USERS_RESPONSE["data"]["users"]["nodes"]


# -------------------------------------------------------------- status list


@respx.mock
def test_status_list_with_team_outputs_team_states(config_path) -> None:
    """Given 已登录且 --team TES 解析为 team UUID
    When 执行 status list --team TES
    Then 以解析出的 teamId 查询 states，stdout 逐项为 id/name/type/position
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route(
        {
            "query Teams": httpx.Response(200, json=TEAMS_RESPONSE),
            "query TeamStates(": httpx.Response(200, json=TEAM_STATES_RESPONSE),
        }
    )

    result = runner.invoke(app, ["status", "list", "--team", "TES", "--format", "json"])

    assert result.exit_code == 0, result.stderr
    assert json.loads(result.output) == TEAM_STATES_RESPONSE["data"]["team"]["states"]["nodes"]
    states_call = next(
        call
        for call in respx.calls
        if json.loads(call.request.content)["query"].startswith("query TeamStates(")
    )
    assert json.loads(states_call.request.content)["variables"] == {
        "teamId": "team-id-tes"
    }


@respx.mock
def test_status_list_without_team_concatenates_all_teams(config_path) -> None:
    """Given 已登录且工作区有一个 Team
    When 执行 status list（不带 --team）
    Then 先查 teams，再逐 team 查 states，输出为各 team 状态的拼接数组
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route(
        {
            "query Teams": httpx.Response(200, json=TEAMS_RESPONSE),
            "query TeamStates(": httpx.Response(200, json=TEAM_STATES_RESPONSE),
        }
    )

    result = runner.invoke(app, ["status", "list", "--format", "json"])

    assert result.exit_code == 0, result.stderr
    assert json.loads(result.output) == TEAM_STATES_RESPONSE["data"]["team"]["states"]["nodes"]
    queries = _sent_queries()
    assert queries[0].startswith("query Teams")
    assert queries[1].startswith("query TeamStates(")


@respx.mock
def test_status_list_unknown_team_not_found(config_path) -> None:
    """Given teams 里没有缩写 ZZZ
    When 执行 status list --team ZZZ
    Then 退出码 1，not_found 信封含原文 ZZZ，且不发 states 查询
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route({"query Teams": httpx.Response(200, json=TEAMS_NO_MATCH_RESPONSE)})

    result = runner.invoke(app, ["status", "list", "--team", "ZZZ"])

    assert result.exit_code == 1
    error = error_envelope(result)
    assert error["type"] == "not_found"
    assert "ZZZ" in "; ".join(error["messages"])
    assert _sent_queries()[0].startswith("query Teams")
    assert len(_sent_queries()) == 1


# --------------------------------------------------------------- label list


@respx.mock
def test_label_list_outputs_all_labels_without_team_field(config_path) -> None:
    """Given 工作区有 workspace 级与 team 级标签
    When 执行 label list
    Then stdout 逐项为 id/name/color（不含内部用于过滤的 team 字段）
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route({"query IssueLabels": httpx.Response(200, json=ISSUE_LABELS_RESPONSE)})

    result = runner.invoke(app, ["label", "list", "--format", "json"])

    assert result.exit_code == 0, result.stderr
    assert json.loads(result.output) == [
        {"id": "label-id-bug", "name": "Bug", "color": "#EB5757"},
        {"id": "label-id-feature", "name": "Feature", "color": "#BB87FC"},
        {"id": "label-id-cli", "name": "cli", "color": "#4EA7FC"},
        {"id": "label-id-other", "name": "other-only", "color": "#999999"},
    ]


@respx.mock
def test_label_list_team_includes_workspace_and_team_labels(config_path) -> None:
    """Given workspace 级标签、TES 的标签与另一 team 的标签并存
    When 执行 label list --team TES
    Then 输出含 workspace 级与 TES 的标签、排除其他 team 的标签（对齐 MCP
    team 参数的「该 team 可用标签全集」语义）
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route(
        {
            "query Teams": httpx.Response(200, json=TEAMS_RESPONSE),
            "query IssueLabels": httpx.Response(200, json=ISSUE_LABELS_RESPONSE),
        }
    )

    result = runner.invoke(app, ["label", "list", "--team", "TES", "--format", "json"])

    assert result.exit_code == 0, result.stderr
    assert json.loads(result.output) == [
        {"id": "label-id-bug", "name": "Bug", "color": "#EB5757"},
        {"id": "label-id-feature", "name": "Feature", "color": "#BB87FC"},
        {"id": "label-id-cli", "name": "cli", "color": "#4EA7FC"},
    ]


@respx.mock
def test_label_list_unknown_team_not_found(config_path) -> None:
    """Given teams 里没有缩写 ZZZ
    When 执行 label list --team ZZZ
    Then 退出码 1，not_found 信封含原文，且不发标签查询
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route(
        {
            "query Teams": httpx.Response(200, json=TEAMS_NO_MATCH_RESPONSE),
        }
    )

    result = runner.invoke(app, ["label", "list", "--team", "ZZZ"])

    assert result.exit_code == 1
    error = error_envelope(result)
    assert error["type"] == "not_found"
    assert "ZZZ" in "; ".join(error["messages"])
    assert len(_sent_queries()) == 1


# ------------------------------------------------------------- label create


@respx.mock
def test_label_create_sends_resolved_team_and_fields(config_path) -> None:
    """Given 已登录且 team TES 存在
    When 执行 label create --team TES --name cli-new --color #123456
    Then mutation input 恰为 {teamId: 解析 UUID, name, color}，stdout 为
    单行 JSON {"id": ..., "name": ...}
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route(
        {
            "query Teams": httpx.Response(200, json=TEAMS_RESPONSE),
            "mutation IssueLabelCreate(": httpx.Response(
                200, json=CREATE_LABEL_RESPONSE
            ),
        }
    )

    result = runner.invoke(
        app,
        [
            "label",
            "create",
            "--team",
            "TES",
            "--name",
            "cli-new",
            "--color",
            "#123456",
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0, result.stderr
    assert json.loads(result.output) == {"id": "label-id-new", "name": "cli-new"}
    variables = json.loads(respx.calls[-1].request.content)["variables"]
    assert variables["input"] == {
        "teamId": "team-id-tes",
        "name": "cli-new",
        "color": "#123456",
    }


@respx.mock
def test_label_create_omits_color_when_unset(config_path) -> None:
    """Given 已登录
    When 执行 label create 不带 --color
    Then input 不含 color 键（可选字段不传空值）
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route(
        {
            "query Teams": httpx.Response(200, json=TEAMS_RESPONSE),
            "mutation IssueLabelCreate(": httpx.Response(
                200, json=CREATE_LABEL_RESPONSE
            ),
        }
    )

    result = runner.invoke(
        app, ["label", "create", "--team", "TES", "--name", "cli-new"]
    )

    assert result.exit_code == 0, result.stderr
    variables = json.loads(respx.calls[-1].request.content)["variables"]
    assert variables["input"] == {"teamId": "team-id-tes", "name": "cli-new"}


@respx.mock
def test_label_create_unknown_team_not_found_before_mutation(config_path) -> None:
    """Given teams 里没有缩写 ZZZ
    When 执行 label create --team ZZZ
    Then 退出码 1，not_found 信封含原文，且不发 mutation
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route({"query Teams": httpx.Response(200, json=TEAMS_NO_MATCH_RESPONSE)})

    result = runner.invoke(
        app, ["label", "create", "--team", "ZZZ", "--name", "x"]
    )

    assert result.exit_code == 1
    error = error_envelope(result)
    assert error["type"] == "not_found"
    assert "ZZZ" in "; ".join(error["messages"])
    assert not any(
        "issueLabelCreate" in json.loads(call.request.content)["query"]
        for call in respx.calls
    )


@respx.mock
def test_label_create_requires_team_and_name(config_path) -> None:
    """Given 已登录
    When label create 缺 --team 或 --name
    Then 报用法错误（exit 2），不调用 API
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)

    no_team = runner.invoke(app, ["label", "create", "--name", "x"])
    no_name = runner.invoke(app, ["label", "create", "--team", "TES"])

    assert no_team.exit_code == 2
    assert no_name.exit_code == 2
    assert not respx.calls


# ------------------------------------------------------------- project list


@respx.mock
def test_project_list_outputs_projects(config_path) -> None:
    """Given 已登录且工作区有一个项目
    When 执行 project list
    Then stdout 为 JSON 数组，逐项为 id/name/state/url
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route({"query Projects": httpx.Response(200, json=PROJECTS_RESPONSE)})

    result = runner.invoke(app, ["project", "list", "--format", "json"])

    assert result.exit_code == 0, result.stderr
    assert json.loads(result.output) == [
        {
            "id": "project-id-1",
            "name": "dotfiles",
            "url": "https://linear.app/acme/project/dotfiles-x1y2",
            "state": "started",
        }
    ]


# --------------------------------------------------------------- cycle list


@respx.mock
def test_cycle_list_with_team_outputs_cycles(config_path) -> None:
    """Given 已登录且 --team TES 解析为 team UUID
    When 执行 cycle list --team TES
    Then 以解析出的 teamId 过滤查询 cycles，stdout 逐项为 id/number/name/
    startsAt/endsAt
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route(
        {
            "query Teams": httpx.Response(200, json=TEAMS_RESPONSE),
            "query Cycles(": httpx.Response(200, json=CYCLES_RESPONSE),
        }
    )

    result = runner.invoke(app, ["cycle", "list", "--team", "TES", "--format", "json"])

    assert result.exit_code == 0, result.stderr
    assert json.loads(result.output) == CYCLES_RESPONSE["data"]["cycles"]["nodes"]
    cycles_call = next(
        call
        for call in respx.calls
        if json.loads(call.request.content)["query"].startswith("query Cycles(")
    )
    assert json.loads(cycles_call.request.content)["variables"] == {
        "teamId": "team-id-tes"
    }


@respx.mock
def test_cycle_list_without_team_concatenates_all_teams(config_path) -> None:
    """Given 已登录且工作区有一个 Team
    When 执行 cycle list（不带 --team）
    Then 先查 teams，再逐 team 查 cycles，输出为各 team cycle 的拼接数组
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route(
        {
            "query Teams": httpx.Response(200, json=TEAMS_RESPONSE),
            "query Cycles(": httpx.Response(200, json=CYCLES_RESPONSE),
        }
    )

    result = runner.invoke(app, ["cycle", "list", "--format", "json"])

    assert result.exit_code == 0, result.stderr
    assert json.loads(result.output) == CYCLES_RESPONSE["data"]["cycles"]["nodes"]
    queries = _sent_queries()
    assert queries[0].startswith("query Teams")
    assert queries[1].startswith("query Cycles(")


# ------------------------------------------------------------- 真实 API 契约


def test_team_list_real_api(config_path, monkeypatch) -> None:
    """Given 真实 API key
    When 执行 team list
    Then 返回非空数组，逐项 id 为 UUID 形态、key/name 为字符串（key 必含，
    MCP 视图缺此字段）
    """
    require_real_api_key(config_path, monkeypatch)

    result = runner.invoke(app, ["team", "list", "--format", "json"])

    assert result.exit_code == 0, result.stderr
    teams = json.loads(result.output)
    assert teams
    for team in teams:
        assert isinstance(team["id"], str) and len(team["id"]) == 36
        assert isinstance(team["key"], str)
        assert isinstance(team["name"], str)


def test_user_list_real_api(config_path, monkeypatch) -> None:
    """Given 真实 API key
    When 执行 user list
    Then 返回非空数组，逐项 id 为 UUID 形态、name/displayName/email 为字符串、
    active 为布尔
    """
    require_real_api_key(config_path, monkeypatch)

    result = runner.invoke(app, ["user", "list", "--format", "json"])

    assert result.exit_code == 0, result.stderr
    users = json.loads(result.output)
    assert users
    for user in users:
        assert isinstance(user["id"], str) and len(user["id"]) == 36
        assert isinstance(user["name"], str)
        assert isinstance(user["displayName"], str)
        assert isinstance(user["email"], str)
        assert isinstance(user["active"], bool)


def test_status_list_real_api(config_path, monkeypatch) -> None:
    """Given 真实 API key 与工作区 team TES
    When 执行 status list --team TES
    Then 返回非空数组，逐项 id 为 UUID 形态、name/type 为字符串、position
    为数值
    """
    require_real_api_key(config_path, monkeypatch)

    result = runner.invoke(app, ["status", "list", "--team", "TES", "--format", "json"])

    assert result.exit_code == 0, result.stderr
    states = json.loads(result.output)
    assert states
    for state in states:
        assert isinstance(state["id"], str) and len(state["id"]) == 36
        assert isinstance(state["name"], str)
        assert isinstance(state["type"], str)
        assert isinstance(state["position"], (int, float))


def test_label_list_real_api(config_path, monkeypatch) -> None:
    """Given 真实 API key
    When 执行 label list
    Then 返回数组（工作区至少有内置标签），逐项 id 为 UUID 形态、name 为
    字符串、color 为 #RRGGBB 形态
    """
    require_real_api_key(config_path, monkeypatch)

    result = runner.invoke(app, ["label", "list", "--format", "json"])

    assert result.exit_code == 0, result.stderr
    labels = json.loads(result.output)
    assert labels
    for label in labels:
        assert isinstance(label["id"], str) and len(label["id"]) == 36
        assert isinstance(label["name"], str)
        assert label["color"].startswith("#") and len(label["color"]) == 7


def test_project_list_real_api(config_path, monkeypatch) -> None:
    """Given 真实 API key
    When 执行 project list
    Then 返回 JSON 数组，逐项 id 为 UUID 形态、name/state 为字符串、url 为
    linear.app 链接
    """
    require_real_api_key(config_path, monkeypatch)

    result = runner.invoke(app, ["project", "list", "--format", "json"])

    assert result.exit_code == 0, result.stderr
    projects = json.loads(result.output)
    for project in projects:
        assert isinstance(project["id"], str) and len(project["id"]) == 36
        assert isinstance(project["name"], str)
        assert isinstance(project["state"], str)
        assert project["url"].startswith("https://linear.app/")


def test_cycle_list_real_api(config_path, monkeypatch) -> None:
    """Given 真实 API key 与工作区 team TES（当前未启用 cycle）
    When 执行 cycle list --team TES
    Then 正常退出，输出为 JSON 数组（无 cycle 时为空数组，字段契约由离线
    测试钉死）
    """
    require_real_api_key(config_path, monkeypatch)

    result = runner.invoke(app, ["cycle", "list", "--team", "TES", "--format", "json"])

    assert result.exit_code == 0, result.stderr
    cycles = json.loads(result.output)
    for cycle in cycles:
        assert isinstance(cycle["id"], str)
        assert isinstance(cycle["number"], int)
        assert cycle["startsAt"].endswith("Z")
        assert cycle["endsAt"].endswith("Z")


def test_label_create_roundtrip_real_api(config_path, monkeypatch) -> None:
    """Given 真实 API key 与唯一 run 标识的标签名
    When label create --team TES --name <run> --color，随后 label list 读回
    Then create 输出 {id, name} 且 id 为 UUID 形态；list 中出现同名标签且
    color 读回一致；断言通过后删除标签清理（失败保留现场）
    """
    api_key = require_real_api_key(config_path, monkeypatch)
    run_id = uuid.uuid4().hex[:8]
    name = f"cli-label-{run_id}"

    try:
        create_result = runner.invoke(
            app,
            [
                "label",
                "create",
                "--team",
                "TES",
                "--name",
                name,
                "--color",
                "#4EA7FC",
                "--format",
                "json",
            ],
        )
        assert create_result.exit_code == 0, create_result.stderr
        label = json.loads(create_result.output)
        assert label == {"id": label["id"], "name": name}
        assert len(label["id"]) == 36

        list_result = runner.invoke(app, ["label", "list", "--format", "json"])
        assert list_result.exit_code == 0, list_result.stderr
        labels = json.loads(list_result.output)
        match = next((l for l in labels if l["name"] == name), None)
        assert match is not None
        assert match["id"] == label["id"]
        assert match["color"] == "#4EA7FC"
    except Exception:
        # 断言失败保留现场，不清理
        raise

    delete_issue_label(api_key, label["id"])

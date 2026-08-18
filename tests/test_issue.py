import json
import uuid

import httpx
import pytest
import respx
from conftest import (
    ACCOUNT_ERROR_RESPONSE,
    CREATE_ISSUE_RESPONSE,
    EMPTY_ISSUES_RESPONSE,
    FAKE_API_KEY,
    GRAPHQL_ERROR_RESPONSE,
    GRAPHQL_URL,
    ISSUE,
    ISSUE_LIST,
    ISSUE_RESPONSE,
    ISSUES_RESPONSE,
    TEAMS_NO_MATCH_RESPONSE,
    TEAMS_RESPONSE,
    error_envelope,
)
from real_api import require_real_api_key
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
def test_create_pretty_outputs_identifier_and_url(config_path) -> None:
    """Given 已登录且 team TES 存在
    When 执行 issue create --pretty
    Then 输出单行「标识 URL」人类可读格式
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
        ["issue", "create", "--team", "TES", "--title", "T", "--body", "B", "--pretty"],
    )

    assert result.exit_code == 0, result.stderr
    assert result.output.strip() == f"TES-123 {ISSUE['url']}"


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
def test_view_pretty_prints_human_readable(config_path) -> None:
    """Given 已登录且目标 issue 存在
    When 执行 issue view --pretty
    Then 输出人类可读格式：首行「标识 标题」，随后为正文原文
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route({"query Issue": httpx.Response(200, json=ISSUE_RESPONSE)})

    result = runner.invoke(app, ["issue", "view", "TES-123", "--pretty"])

    assert result.exit_code == 0, result.stderr
    assert "TES-123 Test issue" in result.output
    assert "Body line 1\nBody line 2" in result.output


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
def test_list_pretty_smoke(config_path) -> None:
    """Given 已登录且工作区有 issue
    When 执行 issue list --pretty
    Then 正常退出且输出非空（rich 表格内容不做字符串断言，见
    tests/ABOUTME.md 渲染层约定）
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route({"query Issues": httpx.Response(200, json=ISSUES_RESPONSE)})

    result = runner.invoke(app, ["issue", "list", "--pretty"])

    assert result.exit_code == 0, result.stderr
    assert result.output.strip()


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

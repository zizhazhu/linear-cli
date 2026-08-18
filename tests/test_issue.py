import json
import uuid

import httpx
import pytest
import respx
from conftest import (
    ACCOUNT_ERROR_RESPONSE,
    CREATE_ISSUE_RESPONSE,
    FAKE_API_KEY,
    GRAPHQL_ERROR_RESPONSE,
    GRAPHQL_URL,
    ISSUE,
    ISSUE_RESPONSE,
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
def test_create_success_outputs_identifier_and_url(config_path) -> None:
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
    assert "TES-123" in result.output
    assert "https://linear.app/" in result.output
    assert "TES-123" in result.output.split()[-1]


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
def test_create_json_output(config_path) -> None:
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

    assert result.exit_code == 0
    assert json.loads(result.output) == {
        "identifier": "TES-123",
        "url": ISSUE["url"],
    }


@respx.mock
def test_view_success_reads_back_title_and_body(config_path) -> None:
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route({"query Issue": httpx.Response(200, json=ISSUE_RESPONSE)})

    result = runner.invoke(app, ["issue", "view", "TES-123"])

    assert result.exit_code == 0, result.stderr
    assert "Test issue" in result.output
    assert "Body line 1\nBody line 2" in result.output


@respx.mock
def test_view_json_returns_full_issue(config_path) -> None:
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route({"query Issue": httpx.Response(200, json=ISSUE_RESPONSE)})

    result = runner.invoke(app, ["issue", "view", "TES-123", "--json"])

    assert result.exit_code == 0, result.stderr
    assert json.loads(result.output) == ISSUE


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
    When create 一条带 run 标识的 issue，并立即用返回标识 view 读回
    Then 标题与正文逐字一致；全部断言通过后归档（失败则保留现场不归档）
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
        ["issue", "create", "--team", "TES", "--title", title, "--body", body, "--json"],
    )
    assert create_result.exit_code == 0, create_result.stderr
    created = json.loads(create_result.output)
    identifier = created["identifier"]

    try:
        assert identifier.startswith("TES-")
        assert created["url"].startswith("https://linear.app/")
        assert identifier in created["url"]

        view_result = runner.invoke(app, ["issue", "view", identifier, "--json"])
        assert view_result.exit_code == 0, view_result.stderr
        read_back = json.loads(view_result.output)
        issue_uuid = read_back["id"]
        assert read_back["title"] == title
        assert read_back["description"] == body
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

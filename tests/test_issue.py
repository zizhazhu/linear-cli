import json
import os
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
)
from typer.testing import CliRunner

from linear_cli import app
from linear_cli.api import archive_issue
from linear_cli.config import save_api_key

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
    # 配置文件不存在（未登录）：提示先执行 linear login，不调用 API
    result = runner.invoke(
        app, ["issue", "create", "--team", "TES", "--title", "T", "--body", "B"]
    )

    assert result.exit_code == 1
    assert "linear login" in result.stderr
    assert not respx.calls


@respx.mock
def test_view_not_logged_in_errors_without_api(config_path) -> None:
    result = runner.invoke(app, ["issue", "view", "TES-123"])

    assert result.exit_code == 1
    assert "linear login" in result.stderr
    assert not respx.calls


@respx.mock
def test_create_unknown_team_errors_without_issuecreate(config_path) -> None:
    # teams 响应里没有 ZZZ：报错包含缩写原文，且不发 issueCreate 调用
    save_api_key(config_path, FAKE_API_KEY)
    _route({"query Teams": httpx.Response(200, json=TEAMS_NO_MATCH_RESPONSE)})

    result = runner.invoke(
        app, ["issue", "create", "--team", "ZZZ", "--title", "T", "--body", "B"]
    )

    assert result.exit_code == 1
    assert "ZZZ" in result.stderr
    sent_queries = [
        json.loads(call.request.content)["query"] for call in respx.calls
    ]
    assert len(sent_queries) == 1
    assert "query Teams" in sent_queries[0]


@respx.mock
def test_create_success_outputs_identifier_and_url(config_path) -> None:
    save_api_key(config_path, FAKE_API_KEY)
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
    save_api_key(config_path, FAKE_API_KEY)
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


@respx.mock
def test_create_json_output(config_path) -> None:
    save_api_key(config_path, FAKE_API_KEY)
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
    save_api_key(config_path, FAKE_API_KEY)
    _route({"query Issue": httpx.Response(200, json=ISSUE_RESPONSE)})

    result = runner.invoke(app, ["issue", "view", "TES-123"])

    assert result.exit_code == 0, result.stderr
    assert "Test issue" in result.output
    assert "Body line 1\nBody line 2" in result.output


@respx.mock
def test_view_json_returns_full_issue(config_path) -> None:
    save_api_key(config_path, FAKE_API_KEY)
    _route({"query Issue": httpx.Response(200, json=ISSUE_RESPONSE)})

    result = runner.invoke(app, ["issue", "view", "TES-123", "--json"])

    assert result.exit_code == 0, result.stderr
    assert json.loads(result.output) == ISSUE


@respx.mock
def test_view_prints_graphql_error_messages_verbatim(config_path) -> None:
    # Linear 返回 errors 时，逐条 message 原文输出到 stderr，不翻译不裁剪
    save_api_key(config_path, FAKE_API_KEY)
    _route({"query Issue": httpx.Response(200, json=GRAPHQL_ERROR_RESPONSE)})

    result = runner.invoke(app, ["issue", "view", "TES-999"])

    assert result.exit_code == 1
    assert "Record not found" in result.stderr
    assert "Secondary error message" in result.stderr


@respx.mock
def test_view_account_error_dumps_raw_body(config_path) -> None:
    # 认证/授权/限流等账号级 GraphQL 错误：message 原文之外再贴原始响应正文
    save_api_key(config_path, FAKE_API_KEY)
    _route({"query Issue": httpx.Response(200, json=ACCOUNT_ERROR_RESPONSE)})

    result = runner.invoke(app, ["issue", "view", "TES-999"])

    assert result.exit_code == 1
    assert "Authentication required, not authenticated" in result.stderr
    assert "AUTHENTICATION_ERROR" in result.stderr  # 只出现在 raw body 里


@respx.mock
def test_view_http_error_prints_raw_body(config_path) -> None:
    # HTTP 非 2xx（如限流 429）：把原始响应正文贴到 stderr
    save_api_key(config_path, FAKE_API_KEY)
    _route(
        {
            "query Issue": httpx.Response(
                429, json={"errors": [{"message": "Rate limit exceeded"}]}
            )
        }
    )

    result = runner.invoke(app, ["issue", "view", "TES-123"])

    assert result.exit_code == 1
    assert "Rate limit exceeded" in result.stderr


def _real_api_key() -> str:
    key = os.environ.get("LINEAR_API_KEY")
    if not key:
        pytest.skip("LINEAR_API_KEY 未设置，跳过真实 API 测试")
    return key


def test_create_view_roundtrip_real_api(config_path) -> None:
    """真实 API：create 一条带 run 标识、含换行/Markdown/保留空白的 issue，
    立即用返回标识 view 读回，标题与正文严格一致；全部断言通过后归档。"""
    api_key = _real_api_key()
    save_api_key(config_path, api_key)
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


def test_view_nonexistent_identifier_real_api(config_path) -> None:
    """真实 API：view 一个格式合法但不存在的标识，
    stderr 包含 Linear 返回的 errors[].message 原文，退出码非 0。"""
    api_key = _real_api_key()
    save_api_key(config_path, api_key)

    result = runner.invoke(app, ["issue", "view", "TES-999999"])

    assert result.exit_code != 0
    assert "Entity not found: Issue" in result.stderr

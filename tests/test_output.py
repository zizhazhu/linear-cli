"""输出层合约：默认 TOON、``--format``、YAML block scalar、错误信封隔离。

T1–T6 对应 LIC-4 的 C1–C6；T7 在 ``test_guide.py``。一律离线，respx
未注册的路由即触网间谍。
"""

import json

import httpx
import pytest
import respx
import yaml
from conftest import (
    CREATE_ISSUE_RESPONSE,
    EMPTY_ISSUES_RESPONSE,
    FAKE_API_KEY,
    GRAPHQL_URL,
    ISSUE,
    ISSUE_RESPONSE,
    LOGIN_OUTPUT,
    TEAMS_NO_MATCH_RESPONSE,
    TEAMS_RESPONSE,
    VIEWER_RESPONSE,
    error_envelope,
)
from toon_format import decode, encode
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


def _stdout(result) -> str:
    """去掉 typer.echo 追加的末尾换行，得到编码器的原文。"""
    return result.output.rstrip("\n")


# ---------------------------------------------------------------- T1 → C1


@respx.mock
def test_default_output_roundtrips_single_object(config_path) -> None:
    """Given 已登录且 team TES 存在
    When 执行 issue create（不带 --format）
    Then 默认 stdout 可被 toon-format decode 还原为原单对象
    （identifier/url）
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route(
        {
            "query Teams": httpx.Response(200, json=TEAMS_RESPONSE),
            "mutation IssueCreate": httpx.Response(200, json=CREATE_ISSUE_RESPONSE),
        }
    )
    expected = {"identifier": "TES-123", "url": ISSUE["url"]}

    result = runner.invoke(
        app, ["issue", "create", "--team", "TES", "--title", "T", "--body", "B"]
    )

    assert result.exit_code == 0, result.stderr
    assert decode(_stdout(result)) == expected


@respx.mock
def test_default_output_roundtrips_uniform_object_list(config_path) -> None:
    """Given 已登录且工作区有一个 Team
    When 执行 team list（不带 --format）
    Then 默认 stdout 可被 toon-format decode 还原为均匀对象列表
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route({"query Teams": httpx.Response(200, json=TEAMS_RESPONSE)})
    expected = [{"id": "team-id-tes", "key": "TES", "name": "Test"}]

    result = runner.invoke(app, ["team", "list"])

    assert result.exit_code == 0, result.stderr
    assert decode(_stdout(result)) == expected


@respx.mock
def test_default_output_roundtrips_multiline_string_object(config_path) -> None:
    """Given 已登录且 issue 正文含换行
    When 执行 issue view（不带 --format）
    Then 默认 stdout 可被 toon-format decode 还原，多行 description 与
    null 字段一并保留
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route({"query Issue": httpx.Response(200, json=ISSUE_RESPONSE)})

    result = runner.invoke(app, ["issue", "view", "TES-123"])

    assert result.exit_code == 0, result.stderr
    assert decode(_stdout(result)) == ISSUE
    assert "\n" in ISSUE["description"]
    assert ISSUE["project"] is None


@respx.mock
def test_default_output_roundtrips_empty_list(config_path) -> None:
    """Given 已登录且查询结果为空
    When 执行 issue list（不带 --format）
    Then 默认 stdout 可被 toon-format decode 还原为空列表
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route({"query Issues": httpx.Response(200, json=EMPTY_ISSUES_RESPONSE)})

    result = runner.invoke(app, ["issue", "list"])

    assert result.exit_code == 0, result.stderr
    assert decode(_stdout(result)) == []


# ---------------------------------------------------------------- T2 → C2


@respx.mock
def test_default_output_equals_toon_encode(config_path) -> None:
    """Given 已登录且目标 issue 存在
    When 执行 issue view（不带 --format）
    Then stdout（去末尾换行）逐字等于 toon-format encode(data)
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route({"query Issue": httpx.Response(200, json=ISSUE_RESPONSE)})

    result = runner.invoke(app, ["issue", "view", "TES-123"])
    json_result = runner.invoke(
        app, ["issue", "view", "TES-123", "--format", "json"]
    )

    assert result.exit_code == 0, result.stderr
    assert json_result.exit_code == 0, json_result.stderr
    assert _stdout(result) == encode(json.loads(json_result.output))


@respx.mock
def test_explicit_format_toon_matches_default(config_path) -> None:
    """Given 已登录且目标 issue 存在
    When 分别执行 issue view 与 issue view --format toon
    Then 两次 stdout 完全一致
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route({"query Issue": httpx.Response(200, json=ISSUE_RESPONSE)})

    default = runner.invoke(app, ["issue", "view", "TES-123"])
    explicit = runner.invoke(app, ["issue", "view", "TES-123", "--format", "toon"])

    assert default.exit_code == 0, default.stderr
    assert explicit.exit_code == 0, explicit.stderr
    assert explicit.output == default.output


# ---------------------------------------------------------------- T3 → C3


@respx.mock
def test_format_json_matches_legacy_single_line(config_path) -> None:
    """Given 已登录且目标 issue 存在
    When 执行 issue view --format json
    Then stdout 与改动前的默认单行 JSON 逐字一致（json.dumps + 换行）
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route({"query Issue": httpx.Response(200, json=ISSUE_RESPONSE)})

    result = runner.invoke(app, ["issue", "view", "TES-123", "--format", "json"])

    assert result.exit_code == 0, result.stderr
    assert result.output.endswith("\n")
    assert result.output[:-1].count("\n") == 0
    assert json.loads(result.output) == ISSUE


@respx.mock
def test_format_json_login_matches_legacy_single_line(config_path) -> None:
    """Given 合法 API key
    When 执行 login --format json
    Then stdout 与改动前的默认单行 JSON 逐字一致
    """
    respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json=VIEWER_RESPONSE))

    result = runner.invoke(
        app, ["login", "--api-key", FAKE_API_KEY, "--format", "json"]
    )

    assert result.exit_code == 0, result.stderr
    assert result.output == json.dumps(LOGIN_OUTPUT, ensure_ascii=False) + "\n"


# ---------------------------------------------------------------- T4 → C4


@respx.mock
def test_format_yaml_uses_block_scalar_for_multiline(config_path) -> None:
    """Given 已登录且 issue 正文含换行
    When 执行 issue view --format yaml
    Then 多行 description 以 YAML block scalar 呈现，且 yaml.safe_load
    还原为原对象
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route({"query Issue": httpx.Response(200, json=ISSUE_RESPONSE)})

    result = runner.invoke(app, ["issue", "view", "TES-123", "--format", "yaml"])

    assert result.exit_code == 0, result.stderr
    assert "description: |" in result.output or "description: |-" in result.output
    assert "Body line 1" in result.output
    assert "Body line 2" in result.output
    assert yaml.safe_load(result.output) == ISSUE


# ---------------------------------------------------------------- T5 → C5


@respx.mock
def test_pretty_flag_is_unknown_option(config_path) -> None:
    """Given 已安装的 linear CLI
    When 任一命令带 --pretty
    Then typer 报未知选项（exit 2），不调用 API
    """
    result = runner.invoke(app, ["issue", "view", "TES-123", "--pretty"])

    assert result.exit_code == 2
    assert "No such option: --pretty" in result.stderr
    assert not respx.calls


# ---------------------------------------------------------------- T6 → C6


@pytest.mark.parametrize("fmt", ["toon", "json", "yaml"])
@respx.mock
def test_error_envelope_ignores_format_flag(fmt: str, config_path) -> None:
    """Given teams 响应里没有缩写 ZZZ
    When 以任意 --format 值执行 issue create --team ZZZ
    Then 退出码 1，stderr 仍为单行 JSON 错误信封（type=not_found），
    不受 --format 影响
    """
    write_api_key_to_config(config_path, FAKE_API_KEY)
    _route({"query Teams": httpx.Response(200, json=TEAMS_NO_MATCH_RESPONSE)})

    result = runner.invoke(
        app,
        [
            "issue",
            "create",
            "--team",
            "ZZZ",
            "--title",
            "T",
            "--body",
            "B",
            "--format",
            fmt,
        ],
    )

    assert result.exit_code == 1
    assert result.stderr.strip().count("\n") == 0
    error = error_envelope(result)
    assert error["type"] == "not_found"
    assert "ZZZ" in "; ".join(error["messages"])

import json
import sys
from pathlib import Path

import httpx
import pytest
import respx
from conftest import (
    FAKE_API_KEY,
    GRAPHQL_URL,
    LOGIN_OUTPUT,
    UNAUTHORIZED_RESPONSE,
    VIEWER,
    VIEWER_RESPONSE,
    error_envelope,
)
from typer.testing import CliRunner

from linear_cli import app

runner = CliRunner()


@respx.mock
def test_login_with_valid_api_key_saves_config(config_path: Path) -> None:
    # 用合法 API key 登录，验证请求携带正确的 Authorization 头，且配置文件被写入
    route = respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json=VIEWER_RESPONSE))

    result = runner.invoke(app, ["login", "--api-key", FAKE_API_KEY])

    assert result.exit_code == 0
    assert config_path.exists()
    assert FAKE_API_KEY in config_path.read_text()
    request = route.calls.last.request
    assert request.headers["Authorization"] == FAKE_API_KEY


@respx.mock
def test_login_defaults_to_json_output(config_path: Path) -> None:
    """Given 合法 API key
    When 执行 login（不带任何输出 flag）
    Then stdout 为单行 JSON：viewer 与 workspace 两个顶层字段，workspace.url
    由 organization.urlKey 推导
    """
    respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json=VIEWER_RESPONSE))

    result = runner.invoke(app, ["login", "--api-key", FAKE_API_KEY])

    assert result.exit_code == 0
    assert json.loads(result.output) == LOGIN_OUTPUT


@respx.mock
def test_login_pretty_prints_human_readable(config_path: Path) -> None:
    """Given 合法 API key
    When 执行 login --pretty
    Then 输出「已登录：Name <email>」人类可读格式
    """
    respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json=VIEWER_RESPONSE))

    result = runner.invoke(app, ["login", "--api-key", FAKE_API_KEY, "--pretty"])

    assert result.exit_code == 0
    assert "已登录：Test User <test@example.com>" in result.output


@respx.mock
def test_login_json_flag_removed_errors(config_path: Path) -> None:
    """Given JSON 已成为默认输出
    When 仍传旧的 --json flag
    Then typer 报用法错误（exit 2），不调用 API
    """
    route = respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json=VIEWER_RESPONSE))

    result = runner.invoke(app, ["login", "--api-key", FAKE_API_KEY, "--json"])

    assert result.exit_code == 2
    assert not route.calls


@respx.mock
def test_login_with_invalid_key_fails_without_saving(config_path: Path) -> None:
    """Given API 对无效 key 返回 HTTP 401
    When 用该 key 登录
    Then 退出码 1，stderr 输出 type 为 http、status 为 401、raw 含原始响应
    正文的错误信封，且不写入配置文件
    """
    respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(401, json=UNAUTHORIZED_RESPONSE))

    result = runner.invoke(app, ["login", "--api-key", FAKE_API_KEY])

    assert result.exit_code == 1
    error = error_envelope(result)
    assert error["type"] == "http"
    assert error["status"] == 401
    assert "Authentication required" in error["raw"]
    assert not config_path.exists()


@respx.mock
def test_login_via_prompt_saves_config(config_path: Path) -> None:
    # 不传 --api-key，通过交互式提示输入 key，验证登录成功且配置文件被写入
    respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json=VIEWER_RESPONSE))

    result = runner.invoke(app, ["login"], input=f"{FAKE_API_KEY}\n")

    assert result.exit_code == 0
    assert config_path.exists()
    assert FAKE_API_KEY in config_path.read_text()


@respx.mock
def test_login_overwrites_existing_config(config_path: Path) -> None:
    # 已登录过旧 key，再次登录应覆盖为新 key，旧 key 不再残留
    old_key = "lin_api_old_key"
    respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json=VIEWER_RESPONSE))
    runner.invoke(app, ["login", "--api-key", old_key])
    assert old_key in config_path.read_text()

    result = runner.invoke(app, ["login", "--api-key", FAKE_API_KEY])

    assert result.exit_code == 0
    content = config_path.read_text()
    assert FAKE_API_KEY in content
    assert old_key not in content


@respx.mock
def test_login_without_config_path_env_uses_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 未设 LINEAR_CONFIG_PATH 时，写入 $XDG_CONFIG_HOME/linear-cli/config.toml
    monkeypatch.delenv("LINEAR_CONFIG_PATH", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json=VIEWER_RESPONSE))

    result = runner.invoke(app, ["login", "--api-key", FAKE_API_KEY])

    assert result.exit_code == 0
    default_config = tmp_path / "linear-cli" / "config.toml"
    assert FAKE_API_KEY in default_config.read_text()


@respx.mock
def test_login_without_xdg_config_home_falls_back_to_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # LINEAR_CONFIG_PATH 与 XDG_CONFIG_HOME 均未设置时，所有平台统一回落到
    # ~/.config/linear-cli/config.toml；重定向 home 的变量因平台而异
    # （Windows 读 USERPROFILE，POSIX 读 HOME）
    monkeypatch.delenv("LINEAR_CONFIG_PATH", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("USERPROFILE" if sys.platform == "win32" else "HOME", str(tmp_path))
    respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json=VIEWER_RESPONSE))

    result = runner.invoke(app, ["login", "--api-key", FAKE_API_KEY])

    assert result.exit_code == 0
    fallback_config = tmp_path / ".config" / "linear-cli" / "config.toml"
    assert FAKE_API_KEY in fallback_config.read_text()

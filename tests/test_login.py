import json
from pathlib import Path

import httpx
import pytest
import respx
from conftest import (
    FAKE_API_KEY,
    GRAPHQL_URL,
    UNAUTHORIZED_RESPONSE,
    VIEWER,
    VIEWER_RESPONSE,
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
def test_login_with_json_flag_outputs_viewer(config_path: Path) -> None:
    # 带 --json 标志登录，验证 stdout 输出的是 viewer 信息的 JSON
    respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json=VIEWER_RESPONSE))

    result = runner.invoke(app, ["login", "--api-key", FAKE_API_KEY, "--json"])

    assert result.exit_code == 0
    assert json.loads(result.output) == VIEWER


@respx.mock
def test_login_with_invalid_key_fails_without_saving(config_path: Path) -> None:
    # 用无效 key 登录（API 返回 401），验证退出码非零且不写入配置文件
    respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(401, json=UNAUTHORIZED_RESPONSE))

    result = runner.invoke(app, ["login", "--api-key", FAKE_API_KEY])

    assert result.exit_code == 1
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
    # 未设 LINEAR_CONFIG_PATH 时，写入默认路径 $XDG_CONFIG_HOME/linear-cli/config.toml
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
    # LINEAR_CONFIG_PATH 与 XDG_CONFIG_HOME 均未设置时，回落到 ~/.config/linear-cli/config.toml
    monkeypatch.delenv("LINEAR_CONFIG_PATH", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json=VIEWER_RESPONSE))

    result = runner.invoke(app, ["login", "--api-key", FAKE_API_KEY])

    assert result.exit_code == 0
    fallback_config = tmp_path / ".config" / "linear-cli" / "config.toml"
    assert FAKE_API_KEY in fallback_config.read_text()

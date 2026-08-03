import os
from pathlib import Path

import pytest
from conftest import FAKE_API_KEY

from linear_cli.config import (
    MissingApiKeyError,
    load_api_key,
    resolve_api_key,
    save_api_key,
)


def test_load_api_key_returns_none_when_file_missing(tmp_path: Path) -> None:
    # 配置文件不存在时应返回 None，而不是抛异常
    assert load_api_key(tmp_path / "config.toml") is None


def test_load_api_key_returns_none_when_key_absent(tmp_path: Path) -> None:
    # 文件存在但没有 api_key 字段时返回 None
    path = tmp_path / "config.toml"
    path.write_text('other = "value"\n')

    assert load_api_key(path) is None


def test_save_then_load_roundtrips_api_key(tmp_path: Path) -> None:
    # save_api_key 写入的 TOML 应能被 load_api_key 原样读回
    path = tmp_path / "nested" / "config.toml"

    save_api_key(path, FAKE_API_KEY)

    assert load_api_key(path) == FAKE_API_KEY


def test_resolve_prefers_cli_key_over_env_and_config(
    config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Given CLI 参数、LINEAR_API_KEY 环境变量、配置文件同时提供不同的 key
    When 调用 resolve_api_key
    Then 返回 CLI 参数的 key
    """
    cli_key = "lin_api_from_cli"
    monkeypatch.setenv("LINEAR_API_KEY", "lin_api_from_env")
    save_api_key(config_path, FAKE_API_KEY)

    assert resolve_api_key(cli_key) == cli_key


def test_resolve_prefers_env_over_config(
    config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Given 无 CLI 参数，LINEAR_API_KEY 环境变量与配置文件同时提供不同的 key
    When 调用 resolve_api_key
    Then 返回环境变量的 key
    """
    env_key = "lin_api_from_env"
    monkeypatch.setenv("LINEAR_API_KEY", env_key)
    save_api_key(config_path, FAKE_API_KEY)

    assert resolve_api_key(None) == env_key


def test_resolve_prefers_env_over_env_file(
    tmp_path: Path, config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Given 无 CLI 参数，LINEAR_API_KEY 环境变量与 .env 文件同时提供不同的 key
    When 调用 resolve_api_key
    Then 返回环境变量的 key
    """
    env_key = "lin_api_from_env"
    monkeypatch.setenv("LINEAR_API_KEY", env_key)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("LINEAR_API_KEY=lin_api_from_dotenv\n")

    assert resolve_api_key(None) == env_key


def test_resolve_reads_env_file_without_mutating_environ(
    tmp_path: Path, config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Given 无 CLI 参数、无 LINEAR_API_KEY 环境变量，cwd 的 .env 文件提供 key
    When 调用 resolve_api_key
    Then 返回 .env 中的 key，且不写入 os.environ（.env 是显式数据源，不是环境变量注入）
    """
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("LINEAR_API_KEY=lin_api_from_dotenv\n")

    assert resolve_api_key(None) == "lin_api_from_dotenv"
    assert os.environ.get("LINEAR_API_KEY") is None


def test_resolve_prefers_env_file_over_config(
    tmp_path: Path, config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Given 无 CLI 参数、无环境变量，.env 文件与配置文件同时提供不同的 key
    When 调用 resolve_api_key
    Then 返回 .env 中的 key
    """
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("LINEAR_API_KEY=lin_api_from_dotenv\n")
    save_api_key(config_path, FAKE_API_KEY)

    assert resolve_api_key(None) == "lin_api_from_dotenv"


def test_resolve_falls_back_to_config(
    tmp_path: Path, config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Given 无 CLI 参数、无环境变量、无 .env（chdir 到干净的临时目录），配置文件提供 key
    When 调用 resolve_api_key
    Then 返回配置文件中的 key
    """
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    save_api_key(config_path, FAKE_API_KEY)

    assert resolve_api_key(None) == FAKE_API_KEY


def test_resolve_raises_when_no_key_available(
    tmp_path: Path, config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Given 无 CLI 参数、无环境变量、无 .env、配置文件不存在
    When 调用 resolve_api_key
    Then 抛出 MissingApiKeyError
    """
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(MissingApiKeyError):
        resolve_api_key(None)

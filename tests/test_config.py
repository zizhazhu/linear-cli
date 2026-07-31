from pathlib import Path

from conftest import FAKE_API_KEY

from linear_cli.config import load_api_key, save_api_key


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

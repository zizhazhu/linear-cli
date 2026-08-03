"""``login`` 命令：验证 API key 并保存凭据。"""

import json

import httpx
import typer

from linear_cli.api import fetch_viewer
from linear_cli.config import get_config_path, write_api_key_to_config


def login(
    api_key: str = typer.Option(
        None,
        "--api-key",
        "-k",
        help="Linear API key；省略则交互式输入。",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="以 JSON 输出 viewer 信息。",
    ),
) -> None:
    """登录 Linear，验证 API key 并保存到本地配置文件。"""
    if not api_key:
        api_key = typer.prompt("API key")

    try:
        viewer = fetch_viewer(api_key)
    except httpx.HTTPStatusError:
        typer.echo("error: API key 验证失败", err=True)
        raise typer.Exit(1) from None

    config_path = get_config_path()
    write_api_key_to_config(config_path, api_key)

    if json_output:
        typer.echo(json.dumps(viewer))
    else:
        typer.echo(f"已登录：{viewer['name']} <{viewer['email']}>")

"""``login`` 命令：验证 API key 并保存凭据。"""

import httpx
import typer

from linear_cli import normalize
from linear_cli.api import GraphQLAPIError, fetch_viewer_and_organization
from linear_cli.config import get_config_path, write_api_key_to_config
from linear_cli.errors import emit_api_error
from linear_cli.output import OutputFormat, OutputOption, emit


def login(
    api_key: str = typer.Option(
        None,
        "--api-key",
        "-k",
        help="Linear API key；省略则交互式输入。",
    ),
    output: OutputOption = OutputFormat.json,
) -> None:
    """登录 Linear，验证 API key 并保存到本地配置文件。"""
    if not api_key:
        api_key = typer.prompt("API key")

    try:
        data = fetch_viewer_and_organization(api_key)
    except (GraphQLAPIError, httpx.HTTPStatusError) as exc:
        emit_api_error(exc)

    config_path = get_config_path()
    write_api_key_to_config(config_path, api_key)

    emit(normalize.login(data), output)

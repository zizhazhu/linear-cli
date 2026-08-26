"""成功路径的 stdout 格式化。

错误信封不走这一层：失败仍由 ``errors.py`` 写成 stderr 单行 JSON。
"""

import json
from enum import Enum
from typing import Any

import typer
import yaml
from toon_format import encode


class OutputFormat(str, Enum):
    """``--format`` 的合法取值；默认 toon。"""

    toon = "toon"
    json = "json"
    yaml = "yaml"


def format_option() -> Any:
    """每个结构化命令各自声明一份，避免共享 Option 实例。"""
    return typer.Option(
        OutputFormat.toon,
        "--format",
        help="Stdout format: toon (default), json, or yaml.",
    )


class _BlockDumper(yaml.SafeDumper):
    """多行字符串用 block scalar，其余走 SafeDumper 默认。"""


def _represent_str(dumper: yaml.SafeDumper, data: str) -> yaml.Node:
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_BlockDumper.add_representer(str, _represent_str)


def render(data: object, fmt: OutputFormat) -> str:
    """把结构化数据编码为选定格式的文本（不含结尾换行）。"""
    if fmt is OutputFormat.json:
        return json.dumps(data, ensure_ascii=False)
    if fmt is OutputFormat.yaml:
        dumped = yaml.dump(
            data,
            Dumper=_BlockDumper,
            allow_unicode=True,
            sort_keys=False,
        )
        return dumped.rstrip("\n")
    return encode(data)


def emit(data: object, fmt: OutputFormat) -> None:
    """把结构化数据写到 stdout。"""
    typer.echo(render(data, fmt))

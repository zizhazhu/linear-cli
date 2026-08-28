"""输出层：把归一化数据按 ``-o/--output`` 渲染到 stdout。

成功输出的渲染集中在这里，命令层只交数据不拼字符串（错误输出的对应层是
:mod:`linear_cli.errors`）。默认 JSON 面向 Agent 与脚本；YAML 是同一份数据
的人类可读视图，不是另一套字段。
"""

import json
from enum import Enum
from typing import Annotated

import typer
import yaml


class OutputFormat(str, Enum):
    """``-o/--output`` 的合法取值。"""

    json = "json"
    yaml = "yaml"


# 各命令共用的选项声明：用 Annotated 才能跨函数复用同一份 flag 定义
OutputOption = Annotated[
    OutputFormat,
    typer.Option(
        "-o",
        "--output",
        help="输出格式：json（默认，单行）或 yaml（同一份数据的多行视图）。",
    ),
]


class _Dumper(yaml.SafeDumper):
    """SafeDumper + 多行文本用块标量。

    issue 正文与评论都是多行 Markdown，默认的折叠引号串会把空行和缩进搅乱，
    正是 YAML 视图要服务的人类读者最在意的部分。
    """


def _represent_str(dumper: yaml.SafeDumper, data: str) -> yaml.ScalarNode:
    """多行文本请求块标量样式；emitter 判定块标量表达不了时自行回落到引号串。"""
    style = "|" if "\n" in data else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


_Dumper.add_representer(str, _represent_str)


def emit(data: object, output: OutputFormat) -> None:
    """把归一化数据渲染到 stdout。

    JSON 为单行、非 ASCII 不转义（Agent 逐行消费，中文原样可读）；YAML 保持
    键序并原样输出非 ASCII，块状风格。两者渲染的是同一份数据，解析后相等。
    """
    if output is OutputFormat.yaml:
        text = yaml.dump(
            data,
            Dumper=_Dumper,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        ).rstrip("\n")
    else:
        text = json.dumps(data, ensure_ascii=False)
    typer.echo(text)

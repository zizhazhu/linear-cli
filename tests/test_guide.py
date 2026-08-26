"""``guide`` 命令的离线测试：静态指南输出，不触网、不需要凭据。"""

import respx
from typer.testing import CliRunner

from linear_cli import app

runner = CliRunner()


@respx.mock
def test_guide_exits_zero_and_describes_io_contract() -> None:
    """Given 已安装的 linear CLI
    When agent 运行 `linear guide`
    Then 退出码为 0，且输出说明 I/O 契约：stdout 默认 TOON、可选 --format
    {toon,json,yaml}、失败时 stderr 仍为单行 JSON 错误信封并以退出码 1
    终止；不再提及 --pretty
    """
    result = runner.invoke(app, ["guide"])

    assert result.exit_code == 0
    assert "--format" in result.output
    assert "toon" in result.output.lower()
    assert "--pretty" not in result.output
    assert '{"error"' in result.output
    assert "auth" in result.output
    assert "not_found" in result.output


@respx.mock
def test_guide_describes_core_workflow() -> None:
    """Given 已安装的 linear CLI
    When agent 运行 `linear guide`
    Then 输出覆盖核心工作流命令：查询层 list、issue create/view/list/update、
    issue comment add
    """
    result = runner.invoke(app, ["guide"])

    assert result.exit_code == 0
    for snippet in (
        "team list",
        "issue create",
        "issue view",
        "issue list",
        "issue update",
        "comment add",
    ):
        assert snippet in result.output


@respx.mock
def test_guide_works_without_credentials(config_path) -> None:
    """Given 未配置任何凭据（config_path fixture 已隔离凭据环境）
    When agent 运行 `linear guide`
    Then 命令照常成功：证明不需要 API key，且不触网（respx 未注册任何路由，
    任何出站请求都会直接失败）
    """
    result = runner.invoke(app, ["guide"])

    assert result.exit_code == 0
    assert result.output.strip()

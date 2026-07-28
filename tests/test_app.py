from typer.testing import CliRunner

from linear_cli import app

runner = CliRunner()


def test_help_shows_usage_and_exits_zero() -> None:
    # --help 应输出用法信息并以退出码 0 正常结束
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Usage" in result.output


def test_no_args_shows_help_and_exits_nonzero() -> None:
    # 不传任何子命令时应显示用法信息，并以非零退出码报错
    result = runner.invoke(app, [])
    assert result.exit_code == 2
    assert "Usage" in result.output

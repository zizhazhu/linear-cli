from typer.testing import CliRunner

from linear_cli import app

runner = CliRunner()


def test_help_shows_usage_and_exits_zero() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Usage" in result.output


def test_no_args_shows_help_and_exits_nonzero() -> None:
    result = runner.invoke(app, [])
    assert result.exit_code == 2
    assert "Usage" in result.output

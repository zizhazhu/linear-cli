import typer

from linear_cli.login import login

app = typer.Typer(
    name="linear",
    help="Linear 命令行工具。",
    no_args_is_help=True,
)


@app.callback()
def callback() -> None:
    """Linear 命令行工具。"""


app.command()(login)


def main() -> None:
    app()

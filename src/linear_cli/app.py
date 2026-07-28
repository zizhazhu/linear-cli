import typer

app = typer.Typer(
    name="linear",
    help="Linear 命令行工具。",
    no_args_is_help=True,
)


@app.callback()
def callback() -> None:
    """Linear 命令行工具。"""


def main() -> None:
    app()

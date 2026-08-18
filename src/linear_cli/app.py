import typer

from linear_cli.issue import issue_app
from linear_cli.login import login
from linear_cli.query import (
    cycle_app,
    label_app,
    project_app,
    status_app,
    team_app,
    user_app,
)

app = typer.Typer(
    name="linear",
    help="Linear 命令行工具。",
    no_args_is_help=True,
)


@app.callback()
def callback() -> None:
    """Linear 命令行工具。"""


app.command()(login)
app.add_typer(issue_app)
app.add_typer(team_app)
app.add_typer(user_app)
app.add_typer(status_app)
app.add_typer(label_app)
app.add_typer(project_app)
app.add_typer(cycle_app)


def main() -> None:
    app()

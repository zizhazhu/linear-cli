"""``guide`` 命令：输出面向 Agent 的使用指南（英文静态文本，不触网、不需要凭据）。"""

import typer

GUIDE = """\
linear-cli — a thin CLI over the Linear GraphQL API, built for agents and scripts.

I/O contract
- Success: single-line JSON on stdout. Every data command takes
  -o/--output json|yaml; -o yaml renders the same data as YAML (multi-line by
  nature, not a line-for-line replacement of the JSON view).
- Execution failure (credentials, name resolution, Linear API, transport):
  single-line JSON on stderr, exit code 1:
  {"error": {"type": ..., ...}} where type is one of
    auth       missing or invalid credentials
    not_found  unresolvable identifier or name (deterministic resolution)
    graphql    Linear API errors; messages[] are the verbatim API messages
    http       transport/status errors; includes status and raw body
- Usage failure (unknown flag, illegal value, missing argument): plain usage
  text on stderr, exit code 2. These are not wrapped in the error envelope,
  so branch on the exit code first, then on error.type.
- `linear guide` itself is offline: no network, no credentials required.

Authentication
- One-time setup: `linear login --api-key lin_api_...`, or export LINEAR_API_KEY.
- Credential resolution order: LINEAR_API_KEY env -> .env file -> config file
  ($LINEAR_CONFIG_PATH -> $XDG_CONFIG_HOME/linear-cli/config.toml
   -> ~/.config/linear-cli/config.toml).

Core workflow
1. Discover values (query layer, one list command each):
     linear team list | user list | project list
     linear status list --team TES
     linear label list --team TES
     linear cycle list --team TES
2. Create:  linear issue create --team TES --title "..." --body "..."
            -> {"identifier": "TES-123", "url": "..."}; --body is stored verbatim.
3. Read:    linear issue view TES-123        (identifier suffices; no team needed)
            linear issue list --team TES --state "In Progress" --assignee me
4. Update:  linear issue update TES-123 --state Done --priority 2 --assignee me
            Partial update: only passed fields change. Name-like values
            (state/assignee/label/project/cycle) resolve to UUIDs client-side
            or fail deterministically with not_found.
5. Report:  linear issue comment add TES-123 --body "progress..."  (verbatim body)
            linear issue comment list TES-123
            linear issue comment delete <comment-uuid>
            --parent <comment-uuid> on add creates a reply.

Tips
- Full flag reference: `linear <command> --help` (e.g. `linear issue list --help`).
- Default outputs are stable single-line JSON — safe to pipe to jq.
- Reach for -o yaml when a human reads the output; keep the default for
  anything a program parses.
- To attach a label that does not exist yet:
  `linear label create --team TES --name <name>` first.
"""


def guide() -> None:
    """输出面向 Agent 的使用指南（英文静态文本）。"""
    typer.echo(GUIDE)

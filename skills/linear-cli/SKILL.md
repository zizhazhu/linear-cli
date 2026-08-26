---
name: linear-cli
description: Manage Linear from the terminal via the local `linear` CLI — list, create, view, and update issues, add comments, and query teams/states/users/labels/projects/cycles. Use whenever a task involves Linear (e.g. "create a Linear issue", "update TES-123", "sync progress to Linear").
---

# linear-cli

Use the `linear` CLI for all Linear operations. It emits TOON on stdout by
default (`--format json|yaml` to opt in) and structured JSON errors on
stderr — built for agent consumption.

## First step

Run `linear guide` before anything else. It prints the full I/O contract
(error envelope, exit codes), credential setup, and the core workflow. That
output is the source of truth — this skill intentionally does not duplicate
it, so the guide and the CLI can never drift apart.

If `linear` is not installed or `linear guide` fails, stop and tell the user
instead of falling back to raw GraphQL/API calls.

## Notes

- Auth is one-time: `linear login --api-key lin_api_...`, or `LINEAR_API_KEY`.
- Full flag reference per command: `linear <command> --help`.

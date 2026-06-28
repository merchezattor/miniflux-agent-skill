# miniflux-agent-cli

A Claude Code **skill** that lets an agent read a Miniflux instance. The skill lives
in [`miniflux-cli/`](miniflux-cli/) and bundles a zero-install, single-file Python CLI
(`miniflux-cli/scripts/miniflux.py`). JSON-only output, designed for AI agents.
Standard library only.

Install by placing the `miniflux-cli/` folder where your agent loads skills (e.g.
`.claude/skills/`), or run the bundled CLI directly as shown below.

## Setup

    export MINIFLUX_BASE_URL="https://reader.example.org"
    export MINIFLUX_API_TOKEN="your-token"

Both can also be passed as `--base-url` / `--token` (args win over env).

## Commands

    python miniflux-cli/scripts/miniflux.py entries [--limit N] [--offset N] [--status unread|read|removed]...
                              [--order FIELD] [--direction asc|desc]
                              [--category ID] [--feed ID] [--search TEXT] [--starred]
    python miniflux-cli/scripts/miniflux.py entry <id>
    python miniflux-cli/scripts/miniflux.py feeds
    python miniflux-cli/scripts/miniflux.py categories [--counts]

`entries` omits each entry's `content`; use `entry <id>` for the full article.

## Exit codes

- `0` success
- `1` API / network / JSON error
- `2` usage / missing config

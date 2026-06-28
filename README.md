# miniflux-agent-cli

A Claude Code **skill** that lets an agent read and triage a Miniflux instance. The skill lives
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
    python miniflux-cli/scripts/miniflux.py fetch-content <id>
    python miniflux-cli/scripts/miniflux.py feeds [--category ID]
    python miniflux-cli/scripts/miniflux.py feed <id>
    python miniflux-cli/scripts/miniflux.py counters
    python miniflux-cli/scripts/miniflux.py categories [--counts]
    python miniflux-cli/scripts/miniflux.py mark read|unread|removed <id> [<id> ...]
    python miniflux-cli/scripts/miniflux.py catch-up [--limit N] [--feed ID] [--category ID]

`entries` omits each entry's `content`; use `entry <id>` (feed content) or
`fetch-content <id>` (full scraped article) to read one. `mark` and `catch-up`
change entry state on the server; all other commands only read.

## Exit codes

- `0` success
- `1` API / network / JSON error
- `2` usage / missing config

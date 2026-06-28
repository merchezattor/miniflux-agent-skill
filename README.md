# miniflux-agent-cli

A Claude Code **skill** that lets an agent read and triage a Miniflux instance. The skill lives
in [`skills/miniflux/`](skills/miniflux/) and bundles a zero-install, single-file Python CLI
(`skills/miniflux/scripts/miniflux.py`). JSON-only output, designed for AI agents.
Standard library only.

Install by placing the `skills/miniflux/` folder where your agent loads skills (e.g.
`.claude/skills/`), or run the bundled CLI directly as shown below.

Requires **Python 3** (no third-party packages) and a reachable Miniflux server
with an API token. Requests time out after 30s.

## Setup

    export MINIFLUX_BASE_URL="https://reader.example.org"
    export MINIFLUX_API_TOKEN="your-token"

Both can also be passed as `--base-url` / `--token` (args win over env).

## Commands

    python skills/miniflux/scripts/miniflux.py entries [--limit N] [--offset N] [--status unread|read|removed]...
                              [--order FIELD] [--direction asc|desc]
                              [--category ID] [--feed ID] [--search TEXT] [--starred]
    python skills/miniflux/scripts/miniflux.py entry <id>
    python skills/miniflux/scripts/miniflux.py fetch-content <id>
    python skills/miniflux/scripts/miniflux.py feeds [--category ID]
    python skills/miniflux/scripts/miniflux.py feed <id>
    python skills/miniflux/scripts/miniflux.py counters
    python skills/miniflux/scripts/miniflux.py categories [--counts]
    python skills/miniflux/scripts/miniflux.py mark read|unread|removed <id> [<id> ...]
    python skills/miniflux/scripts/miniflux.py catch-up [--limit N] [--feed ID] [--category ID]

`entries` omits each entry's `content`; use `entry <id>` (feed content) or
`fetch-content <id>` (full scraped article) to read one. `mark` and `catch-up`
change entry state on the server; all other commands only read.

## Exit codes

- `0` success
- `1` API / network / JSON error (includes a 30s request timeout)
- `2` usage / missing config

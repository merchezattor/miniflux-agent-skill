# miniflux-agent-cli

Zero-install, single-file Python CLI for reading a Miniflux instance.
JSON-only output, designed for AI agents. Standard library only.

## Setup

    export MINIFLUX_BASE_URL="https://reader.example.org"
    export MINIFLUX_API_TOKEN="your-token"

Both can also be passed as `--base-url` / `--token` (args win over env).

## Commands

    python miniflux.py entries [--limit N] [--offset N] [--status unread|read|removed]...
                              [--order FIELD] [--direction asc|desc]
                              [--category ID] [--feed ID] [--search TEXT] [--starred]
    python miniflux.py entry <id>
    python miniflux.py feeds
    python miniflux.py categories [--counts]

`entries` omits each entry's `content`; use `entry <id>` for the full article.

## Exit codes

- `0` success
- `1` API / network / JSON error
- `2` usage / missing config

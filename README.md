# miniflux-agent-cli

A Claude Code **skill** that lets an agent read, browse, search, summarize, and
triage a [Miniflux](https://miniflux.app) RSS instance. It bundles a zero-install,
single-file Python CLI ([`skills/miniflux/scripts/miniflux.py`](skills/miniflux/scripts/miniflux.py))
with JSON-only output, designed to be driven by an AI agent rather than a human.

The skill is read-mostly: every command only reads except `mark` and `catch-up`,
which change entry state on the server.

## Setup

### Required environment variables

| Variable | Description |
| --- | --- |
| `MINIFLUX_BASE_URL` | Base URL of your Miniflux server, e.g. `https://reader.example.org`. |
| `MINIFLUX_API_TOKEN` | A Miniflux API token (Settings → API Keys). Sent as the `X-Auth-Token` header. |

Requires **Python 3** (standard library only — nothing to install) and a reachable
Miniflux server. Requests time out after 30s.

### Install the skill

```
npx skills add merchezattor/miniflux-agent-skill
```

## Commands

Listing of every command with its parameters. The agent invokes these; you don't
need to run them by hand.

- **`entries`** — scan a list of entries (titles, ids, feeds, timestamps; article
  bodies stripped to stay cheap).
  Params: `[--limit N]`, `[--offset N]`, `[--status unread|read|removed]` (repeatable),
  `[--order FIELD]`, `[--direction asc|desc]`, `[--category ID]`, `[--feed ID]`,
  `[--search TEXT]`, `[--starred]`.
- **`entry <id>`** — one entry with its **full feed content**. No params.
- **`fetch-content <id>`** — the **full scraped original article**; use when an
  entry's content is truncated or empty. No params.
- **`feeds`** — every subscribed feed (id, title, category, …).
  Params: `[--category ID]`.
- **`feed <id>`** — details for one feed. No params.
- **`counters`** — unread/read counts per feed id; cheap triage. No params.
- **`categories`** — all categories. Params: `[--counts]` (adds `unread_count` /
  `total_count`).
- **`mark <status> <id> [<id> …]`** — *(write)* set one or more entries to `read`,
  `unread`, or `removed`.
- **`catch-up`** — *(write)* fetch unread entries, **mark them read**, and return them.
  Params: `[--limit N]`, `[--feed ID]`, `[--category ID]` (`--feed` wins over
  `--category`).

`--category` and `--feed` take **numeric ids**, so the agent resolves names via
`categories` / `feeds` first.

## Workflows

The skill is built around a **scan cheap, then drill** pattern: list many entries
without bodies, then pull full content only for the few that matter.

- **Summarize what's unread** — `entries --status unread` to scan titles, then
  `entry <id>` for the noteworthy ones; summarize.
- **Anything new in a category** — `categories` to find the id → `entries --category <id> --status unread`.
- **Search the reader** — `entries --search "<query>"` → present matches, drill in on request.
- **Show starred articles** — `entries --starred`.
- **What did a blog publish lately** — `feeds` to find the id → `entries --feed <id> --order published_at`.
- **Catch me up and clear unread** — `catch-up` (optionally `--feed` / `--category`) drains and marks read in one step.
- **Quick triage** — `counters` to see which feeds have new items before paging entries.


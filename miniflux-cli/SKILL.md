---
name: miniflux-cli
description: >-
  Read, browse, search, summarize, and triage the user's Miniflux RSS reader by
  driving the repo's miniflux.py CLI. Use this whenever the user wants to catch
  up on their feeds or articles — e.g. "what's unread", "summarize my feeds",
  "any new articles in <category>", "search my reader for X", "show my starred",
  "what did <site> publish lately", "catch me up and mark as read" — even when
  they don't mention Miniflux or the CLI by name.
required_environment_variables:
  - MINIFLUX_BASE_URL
  - MINIFLUX_API_TOKEN
---

# Miniflux CLI

This skill bundles `scripts/miniflux.py` — a zero-dependency CLI for browsing a
Miniflux RSS instance. Run it as `python3 scripts/miniflux.py <command>` (path
relative to this skill's directory; from the repo root that's
`python3 miniflux-cli/scripts/miniflux.py`). Results are pretty-printed JSON on
**stdout**; errors go to **stderr**. Most commands only read, but `mark` and
`catch-up` **change entry state on the server** — see "Commands that change state"
below.

## Auth

The CLI needs a base URL and an API token. They resolve in this order (flags win
over environment):

- `MINIFLUX_BASE_URL` env var, or `--base-url https://reader.example.org`
- `MINIFLUX_API_TOKEN` env var, or `--token <token>`

If either is missing the CLI exits `2` with a message like
`Missing base URL: set --base-url or MINIFLUX_BASE_URL`. When you see exit `2`,
stop and tell the user to set the env vars or pass the flags — don't invent a token.

## Commands

```
python3 scripts/miniflux.py entries [--limit N] [--offset N]
                                    [--status unread|read|removed]   # repeatable
                                    [--order FIELD] [--direction asc|desc]
                                    [--category ID] [--feed ID]
                                    [--search TEXT] [--starred]
python3 scripts/miniflux.py entry <id>
python3 scripts/miniflux.py fetch-content <id>
python3 scripts/miniflux.py feeds [--category ID]
python3 scripts/miniflux.py feed <id>
python3 scripts/miniflux.py counters
python3 scripts/miniflux.py categories [--counts]
python3 scripts/miniflux.py mark read|unread|removed <id> [<id> ...]
python3 scripts/miniflux.py catch-up [--limit N] [--feed ID] [--category ID]
```

- **`entries`** → `{"total": N, "entries": [...]}`. Each entry's `content` field is
  **stripped** to keep the payload small. Defaults: `--limit 20 --offset 0
  --order published_at --direction desc`. `--status` may be given more than once
  (e.g. `--status unread --status read`). `--feed ID` lists only that feed's entries.
- **`entry <id>`** → a single entry **with full `content`** (the article HTML/text).
- **`fetch-content <id>`** → `{"content": ...}` with the **full scraped original
  article**. Use when an `entry`'s `content` is truncated or empty. Third drill
  level after `entries` (no content) and `entry` (feed content).
- **`feeds [--category ID]`** → every subscribed feed (each has an `id`, `title`,
  `category`, ...), or only that category's feeds.
- **`feed <id>`** → one feed's details.
- **`counters`** → unread/read counts per feed id. Cheap triage to find which
  feeds have new items without paging entries.
- **`categories`** → all categories. Add `--counts` for `unread_count` / `total_count`
  per category.

## The core pattern: scan cheap, then drill

`entries` deliberately drops article bodies because listing many full articles burns
a lot of tokens for little benefit. Work in two steps:

1. **Scan** with `entries` to see titles, ids, feeds, and timestamps.
2. **Drill** into a specific article with `entry <id>` **only when you actually need
   the full text** (e.g. to summarize or quote it).

Avoid calling `entry <id>` in a loop over many entries. If the user wants a digest of
N articles, fetch full content only for the ones that matter, and prefer titles +
summaries from the `entries` list when that's enough to answer.

## Commands that change state

Unlike the read commands, these mutate the server:

- **`mark <status> <id...>`** sets one or more entries to `read`, `unread`, or
  `removed`. Example: `mark read 123 456`. Prints `{"entry_ids": [...],
  "status": "..."}` on success.
- **`catch-up [--limit N] [--feed ID] [--category ID]`** fetches unread entries,
  **marks them read**, and returns them (content stripped, like `entries`). Use it
  for "catch me up and clear my unread". It marks before returning, so a
  successful result means those entries are now read. With no unread it returns
  `[]` and changes nothing. When both `--feed` and `--category` are given, `--feed`
  wins. Default `--limit` is 100.

Only run these when the user actually wants their reader's state changed. For
read-only browsing, prefer `entries --status unread`.

## Resolving names to IDs

`--category` and `--feed` take **numeric ids**, not names. When the user names a
category or feed in words, first look it up:

- Category: run `categories` (or `categories --counts`), match the `title`, take its `id`.
- Feed: run `feeds`, match the `title` or site URL, take its `id`.

Then filter: `entries --category <id>` or `entries --feed <id>`.

## Worked workflows

**"Summarize what's unread."**
`entries --status unread --limit 30` → scan titles. Pick the noteworthy ones, fetch
each with `entry <id>`, and summarize. Don't pull full content for all 30.

**"Anything new in my Tech category?"**
`categories` → find `Tech`'s id → `entries --category <id> --status unread`.

**"Search my reader for Kubernetes."**
`entries --search "Kubernetes"` → present matching titles/feeds; drill in on request.

**"Show my starred articles."**
`entries --starred`.

**"What did <a specific blog> publish recently?"**
`feeds` → find that feed's id → `entries --feed <id> --order published_at`.

**Paging through a lot of entries.**
Increase `--limit`, or step with `--offset` (`--offset 20`, `--offset 40`, ...). Use
`total` in the response to know when you've seen everything.

## Exit codes

- `0` — success; parse the JSON on stdout.
- `1` — API, network, or JSON error. The stderr message includes Miniflux's own
  `error_message` when available (e.g. a bad token or unreachable host). Report it;
  don't silently retry.
- `2` — usage error or missing config (no base URL / token). Fix the invocation or
  ask the user for credentials.

---
name: miniflux-cli
description: >-
  Read, browse, search, and summarize the user's Miniflux RSS reader by driving
  the repo's read-only miniflux.py CLI. Use this whenever the user wants to catch
  up on their feeds or articles — e.g. "what's unread", "summarize my feeds",
  "any new articles in <category>", "search my reader for X", "show my starred",
  "what did <site> publish lately" — even when they don't mention Miniflux or the
  CLI by name.
required_environment_variables:
  - MINIFLUX_BASE_URL
  - MINIFLUX_API_TOKEN
---

# Miniflux CLI

This skill bundles `scripts/miniflux.py` — a zero-dependency, **read-only** CLI for
browsing a Miniflux RSS instance. Run it as `python3 scripts/miniflux.py <command>`
(path relative to this skill's directory; from the repo root that's
`python3 miniflux-cli/scripts/miniflux.py`). Results are pretty-printed JSON on
**stdout**; errors go to **stderr**. Nothing it does mutates the server, so it is
always safe to run.

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
python3 scripts/miniflux.py feeds
python3 scripts/miniflux.py categories [--counts]
```

- **`entries`** → `{"total": N, "entries": [...]}`. Each entry's `content` field is
  **stripped** to keep the payload small. Defaults: `--limit 20 --offset 0
  --order published_at --direction desc`. `--status` may be given more than once
  (e.g. `--status unread --status read`). `--feed ID` lists only that feed's entries.
- **`entry <id>`** → a single entry **with full `content`** (the article HTML/text).
- **`feeds`** → every subscribed feed (each has an `id`, `title`, `category`, ...).
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

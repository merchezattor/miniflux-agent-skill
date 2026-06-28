# Miniflux Agent CLI — Design (PoC)

**Date:** 2026-06-28
**Status:** Approved for implementation

## Goal

A zero-install, single-file Python CLI that lets AI agents (and humans) read data
from a Miniflux instance. Output is JSON-only and token-light by default so agents
can parse it directly without scraping or drowning in full article HTML.

## Non-goals (PoC)

- Write operations (mark read/unread, star, create/delete feeds).
- Config file support.
- Pagination helpers beyond raw `--limit`/`--offset`.
- Packaging/distribution polish (pipx, entry points). Run via `python miniflux.py`.

## Architecture

Single file: `miniflux.py`. Python 3 standard library only
(`argparse`, `urllib.request`, `urllib.parse`, `urllib.error`, `json`, `os`, `sys`).

Three layers:

1. **Config resolution.** Base URL and token come from CLI args
   (`--base-url`, `--token`), falling back to environment variables
   (`MINIFLUX_BASE_URL`, `MINIFLUX_API_TOKEN`). Args take precedence.
   If either is missing after resolution, print an error to stderr and exit 2.
   The base URL is normalized by stripping a trailing `/`.

2. **HTTP client.** A single helper `request(method, path, params=None)`:
   - Builds the URL as `{base_url}/v1/{path}` with a urlencoded query string.
   - Sets header `X-Auth-Token: {token}`.
   - Parses the JSON response body and returns it.
   - Maps `urllib.error.HTTPError` (401/403/404/etc.) and `URLError`
     (connection failures) to a clean stderr message and exit code 1.

3. **Commands.** `argparse` subparsers dispatch to one function per command.

## Commands

| Command        | Maps to                  | Behavior |
|----------------|--------------------------|----------|
| `entries`      | `GET /v1/entries`        | List recent entries. Strips `content` from each item. |
| `entry <id>`   | `GET /v1/entries/{id}`   | Single entry, full payload **including** `content`. |
| `feeds`        | `GET /v1/feeds`          | List all feeds (as returned by Miniflux). |
| `categories`   | `GET /v1/categories`     | List categories. `--counts` adds `?counts=true` (unread/total per category). |

### `entries` flags

- `--limit` (int, default 20)
- `--offset` (int, default 0)
- `--status` (choices: `unread`, `read`, `removed`; repeatable — sent as multiple `status` params)
- `--order` (e.g. `id`, `status`, `published_at`, `category_title`, `category_id`)
- `--direction` (`asc` | `desc`; default `desc`)
- `--category <id>` (int) → `category_id`
- `--feed <id>` (int) → when given, the request targets `GET /v1/feeds/{id}/entries` (all other entry flags still apply as query params)
- `--search <text>`
- `--starred` (flag)

Default behavior with no flags: latest 20 entries, newest first.

## Output contract

- **stdout:** JSON only.
  - `entries` → `{"total": N, "entries": [...]}` with `content` removed from each entry.
  - `entry` → single JSON object (full).
  - `feeds` → JSON array.
  - `categories` → JSON array.
  - JSON is pretty-printed with `indent=2` for readability; agents parse regardless.
- **stderr:** human-readable error messages only. Never mixed into stdout.
- **Exit codes:** `0` success, `1` API/HTTP/network error, `2` usage/config error.

## Rationale: stripping `content` in lists

Each entry's `content` field is the full article body as HTML — often thousands of
tokens. Multiplied across a 20-item list this dominates the response. Lists return
metadata only (id, title, url, author, published_at, status, feed info, etc.);
`entry <id>` is the deliberate path to full content for a single item.

## Error handling

- Missing/invalid config → stderr message naming the missing var/arg, exit 2.
- HTTP error status → stderr message including status code and, when present, the
  Miniflux `error_message` from the response body, exit 1.
- Network failure (DNS, refused, timeout) → stderr message, exit 1.
- Malformed/non-JSON response → stderr message, exit 1.

## Testing / verification

PoC verification is manual against a live instance using real
`MINIFLUX_BASE_URL` / `MINIFLUX_API_TOKEN`:

1. `python miniflux.py feeds` → returns feed array.
2. `python miniflux.py categories --counts` → categories with counts.
3. `python miniflux.py entries --limit 3` → 3 entries, no `content` field present.
4. `python miniflux.py entry <id>` (id from step 3) → full entry incl. `content`.
5. Unset token → exits 2 with a clear message.

Automated mock-based tests are deferred; they can be added without changing the
public interface.

## Future extensions (not now)

- Write commands: mark read/unread, toggle star, refresh feed.
- `--fields` selection and content truncation/preview modes.
- Config file and named profiles for multiple instances.
- Proper packaging with a `miniflux` console entry point.

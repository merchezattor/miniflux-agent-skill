# Design: New Miniflux CLI commands (read drill-down + write)

Date: 2026-06-28

## Context

`miniflux-cli/scripts/miniflux.py` is a single-file, stdlib-only CLI an agent
uses to read a Miniflux instance. Today it exposes four read-only GET commands:
`entries` (content stripped), `entry` (full content), `feeds`, `categories`.
Its design contract is "scan cheap, then drill": `entries` strips `content` so
agents scan titles/ids cheaply, then pull `entry <id>` only for what they read.

This change adds drill-down reads, cheap triage, and — for the first time —
**write** commands. The previous "read-only / always safe to run" promise in
`SKILL.md` is intentionally dropped: the tool becomes read-mostly with two
mutating commands.

## Goals

Add six new/changed commands plus the request-body plumbing they need, keeping
the five parallel surfaces (impl, `SKILL.md`, `README.md`, tests, `evals.json`)
in sync.

## Commands

### Read (GET)

1. **`fetch-content <id>`** → `GET entries/{id}/fetch-content`
   Scrapes and returns the full original article when the feed's `content` is
   truncated. The third drill level after `entries` (no content) and
   `entry` (feed content). Returns the API object as-is (e.g. `{"content": ...}`).

2. **`counters`** → `GET feeds/counters`
   Returns unread/read counts keyed by feed id. Cheap triage — "which feeds have
   new items?" without paging entries. Returns the API object as-is.

3. **`feed <id>`** → `GET feeds/{id}`
   One feed's details. Singular `feed` complements the existing plural `feeds`.

4. **`feeds --category <id>`** → `GET categories/{id}/feeds`
   Extends the existing `feeds` command rather than adding a new one. When
   `--category` is given, the path switches to `categories/{id}/feeds`; otherwise
   it stays `feeds`. This mirrors how `entries --feed` already switches its path.

### Write (PUT)

5. **`mark <status> <id...>`** → `PUT entries`
   Marks one or many entries. `status` is a positional choice
   (`read|unread|removed`); `id...` is one or more entry ids. Request body:
   `{"entry_ids": [<ids>], "status": "<status>"}`. The API returns `204 No
   Content`; the command echoes `{"entry_ids": [...], "status": "..."}` to stdout
   so the "stdout is JSON on success" contract holds.

### Read + write composition

6. **`catch-up [--feed <id>] [--category <id>] [--limit N]`**
   Fetch unread, mark read, return them. No single Miniflux endpoint does this;
   it composes two calls. Behavior:
   - `GET entries` with `status=unread` plus any of `--feed` (switches path to
     `feeds/{id}/entries`), `--category` (`category_id` param), `--limit`. These
     reuse `entries`' exact filtering semantics. All are optional and may be
     combined, but because `--feed` switches the request path to a single feed's
     entries (which the `category_id` param does not further constrain),
     **`--feed` takes precedence when both `--feed` and `--category` are given.**
     A feed belongs to exactly one category, so the two filters together are
     either redundant or empty; this precedence makes that case well-defined.
   - Collect the returned entry ids.
   - If there are ids: `PUT entries {"entry_ids": ids, "status": "read"}`.
   - Return the entries with `content` stripped (same scan model as `entries`),
     so it stays cheap; the agent can still `entry <id>` / `fetch-content <id>`
     afterward since ids are unchanged.
   - **Order:** mark first, return only if the mark succeeded. The returned set
     then carries the guarantee "these are now read." If the PUT raises, print
     nothing and exit non-zero.
   - **Empty case:** no unread → return `[]`, skip the PUT entirely (an empty
     `entry_ids` is a pointless/erroring call).

## Infrastructure changes

`api_request(base_url, token, method, path, params=None, data=None)`:

- New optional `data`. When present, `json.dumps(data)`, encode UTF-8, pass as
  the request body, and add header `Content-Type: application/json`. Stdlib only.
- **Empty-response handling:** `PUT entries` returns `204` with an empty body.
  After reading the body, if it is empty return `None` instead of calling
  `json.loads` (which currently raises "Invalid JSON response from server").

The `call` closure in `main()` and the `call` fakes in tests gain the `data`
parameter. Command handlers continue to take `(args, call)`.

## Output & error contract (unchanged)

- stdout is JSON on success; errors go to stderr.
- Exit codes: `1` = API/network/JSON failure, `2` = usage/missing config.
- `mark` echoes a confirmation object; `catch-up` returns the entry list (or
  `[]`); GET commands return the API payload as-is.

## Non-goals (explicitly deferred)

- `mark-all-as-read` (feed/category/user), toggle bookmark/star, and feed refresh
  are **not** in this round. They can be added later as a separate decision.
- No retry/transaction semantics beyond "mark before return" in `catch-up`.

## Surfaces to update

1. `miniflux-cli/scripts/miniflux.py` — implementation
2. `miniflux-cli/SKILL.md` — agent instructions; rewrite the read-only / "always
   safe to run" promise to reflect two mutating commands; document new commands,
   workflows (triage via `counters`, drill via `fetch-content`, drain via
   `catch-up`), and that `mark`/`catch-up` change state.
3. `README.md` — human-facing summary
4. `tests/test_miniflux.py` — coverage for each command, the `data`/`204` plumbing,
   `feeds --category` path switch, and `catch-up` order + empty case
5. `miniflux-cli/evals/evals.json` — skill-triggering evals if prompt-relevant
   behavior changed

## Testing approach

Follow existing patterns: inject a fake `call` that records `(method, path,
params, data)` for command-logic tests; mock `miniflux.urllib.request.urlopen`
for `api_request` plumbing (body encoding, `Content-Type`, `204` → `None`).
No live server, no third-party deps.

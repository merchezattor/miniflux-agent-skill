# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Claude Code **skill** (`skills/miniflux/`) that lets an agent read and triage a
Miniflux RSS instance. The skill bundles a single-file, **read-mostly**,
standard-library-only Python CLI (`skills/miniflux/scripts/miniflux.py`): every command
is a GET except `mark` and `catch-up`, which change entry state. It is installed by
dropping `skills/miniflux/`
where an agent loads skills (e.g. `.claude/skills/`). There is no package, no
dependencies, and no build step — `miniflux.py` is the entire product.

## Commands

```bash
# Run the full test suite (stdlib unittest — pytest is NOT used/installed)
python3 -m unittest discover -s tests -v

# Run a single test class or method
python3 -m unittest tests.test_miniflux.TestResolveConfig -v
python3 -m unittest tests.test_miniflux.TestCmdEntries.test_feed_filter_changes_path -v

# Run the CLI (from repo root)
python3 skills/miniflux/scripts/miniflux.py feeds
python3 skills/miniflux/scripts/miniflux.py entries --status unread --limit 30
```

Auth comes from `MINIFLUX_BASE_URL` + `MINIFLUX_API_TOKEN` (or `--base-url` / `--token`
flags, which win over env). `.env` holds local credentials and is gitignored.

## Architecture

`miniflux.py` is deliberately flat and dependency-injected for testability:

- **`api_request(base_url, token, method, path, params)`** is the only network boundary.
  It builds `{base_url}/v1/{path}`, sets the `X-Auth-Token` header, and normalizes all
  failures into `MinifluxError`. `urlencode(..., doseq=True)` is what lets repeatable
  params like `--status unread --status read` become multiple query args.
- **`cmd_*` handlers take a `call` callable**, not the network code directly. `main()`
  closes `api_request` over the resolved config and passes it in; tests pass a fake
  `call` that captures the method/path/params. This is the core testing seam — exercise
  command logic without HTTP.
- **`MinifluxError` carries an `exit_code`** (1 = API/network/JSON failure, 2 =
  usage/missing config). `main()` is the single place that catches it, prints to stderr,
  and returns the code. Keep this contract: stdout is JSON-only on success; everything
  else goes to stderr with the right exit code.

### The "scan cheap, then drill" contract

`cmd_entries` strips the `content` field from every entry via `strip_content` (which
returns a copy and never mutates input). `cmd_entry` keeps full `content`. This is
intentional: agents `entries` to scan titles/ids/timestamps cheaply, then `entry <id>`
only for articles they actually need to read. Preserve this asymmetry — it's the whole
token-efficiency design, documented for the agent in `skills/miniflux/SKILL.md`.

### Filtering by feed vs. everything else

In `cmd_entries`, `--feed ID` switches the path to `feeds/{id}/entries`; all other
filters (`--category`, `--search`, `--starred`, `--status`) are query params on the
plain `entries` path. `--category`/`--feed` take **numeric ids**, so the agent must
resolve names via `categories`/`feeds` first (see SKILL.md workflows).

## Conventions

- **Standard library only.** No third-party imports in `miniflux.py` or the tests — this
  is a hard constraint that keeps the skill zero-install. `.format()` strings (not
  f-strings) are used throughout for broad-runtime portability.
- **Read-mostly.** Every command is a GET except `mark` and `catch-up` (both PUT
  `entries`). Adding further mutating endpoints is a deliberate decision — keep the
  read commands free of side effects, and document any new writes in SKILL.md's
  "Commands that change state" section.
- Tests mock at `miniflux.urllib.request.urlopen` (the real boundary) or inject a fake
  `call`; follow that pattern rather than hitting a live server.

## Two parallel surfaces to keep in sync

When you change the CLI's flags, output shape, or exit codes, update **all** of:

1. `skills/miniflux/scripts/miniflux.py` — the implementation
2. `skills/miniflux/SKILL.md` — the agent-facing instructions (commands, workflows, exit codes)
3. `README.md` — the human-facing summary
4. `tests/test_miniflux.py` — coverage
5. `skills/miniflux/evals/evals.json` — skill-triggering evals, if behavior the prompts rely on changes

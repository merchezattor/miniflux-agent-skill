# Miniflux Agent CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a zero-install, single-file Python CLI (`miniflux.py`) that reads entries, feeds, and categories from a Miniflux instance and emits token-light JSON for AI agents.

**Architecture:** One module, `miniflux.py`, with pure helpers (config resolution, content stripping), one HTTP helper over `urllib`, four command handlers that take an injected `call` callable (so they test without network), and an `argparse` `main` that wires config → handler → JSON stdout. Tests use stdlib `unittest` + `unittest.mock`.

**Tech Stack:** Python 3 standard library only — `argparse`, `urllib.request`/`parse`/`error`, `json`, `os`, `sys`. Tests: `unittest`, `unittest.mock`.

## Global Constraints

- Python 3 **standard library only** — no third-party runtime or test dependencies (`pip install` must not be required).
- Output: **JSON only on stdout**, pretty-printed with `json.dumps(..., indent=2)`. Errors go to **stderr only**.
- Exit codes: `0` success, `1` API/HTTP/network/JSON error, `2` usage/config error.
- Config precedence: CLI arg > env var. Env vars: `MINIFLUX_BASE_URL`, `MINIFLUX_API_TOKEN`. Base URL trailing `/` stripped.
- Auth header: `X-Auth-Token: <token>`. API base path: `{base_url}/v1/{path}`.
- `entries` list responses must have `content` removed from every entry; `entry <id>` keeps it.
- Tests run from repo root with: `python -m unittest discover -s tests -v`.

---

### Task 1: Scaffold + config resolution

**Files:**
- Create: `miniflux.py`
- Create: `tests/test_miniflux.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `class MinifluxError(Exception)` with attribute `.exit_code: int` (default `1`).
  - `resolve_config(arg_base_url: str|None, arg_token: str|None, env: Mapping) -> tuple[str, str]` returning `(base_url, token)`; raises `MinifluxError(exit_code=2)` when either is missing. Base URL has trailing `/` stripped.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_miniflux.py`:

```python
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import miniflux  # noqa: E402


class TestResolveConfig(unittest.TestCase):
    def test_args_take_precedence_over_env(self):
        env = {"MINIFLUX_BASE_URL": "https://env.example", "MINIFLUX_API_TOKEN": "envtok"}
        base, token = miniflux.resolve_config("https://arg.example", "argtok", env)
        self.assertEqual(base, "https://arg.example")
        self.assertEqual(token, "argtok")

    def test_falls_back_to_env(self):
        env = {"MINIFLUX_BASE_URL": "https://env.example", "MINIFLUX_API_TOKEN": "envtok"}
        base, token = miniflux.resolve_config(None, None, env)
        self.assertEqual(base, "https://env.example")
        self.assertEqual(token, "envtok")

    def test_strips_trailing_slash(self):
        env = {"MINIFLUX_API_TOKEN": "t"}
        base, _ = miniflux.resolve_config("https://x.example/", None, env)
        self.assertEqual(base, "https://x.example")

    def test_missing_base_url_exits_2(self):
        with self.assertRaises(miniflux.MinifluxError) as ctx:
            miniflux.resolve_config(None, "t", {})
        self.assertEqual(ctx.exception.exit_code, 2)

    def test_missing_token_exits_2(self):
        with self.assertRaises(miniflux.MinifluxError) as ctx:
            miniflux.resolve_config("https://x.example", None, {})
        self.assertEqual(ctx.exception.exit_code, 2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest discover -s tests -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'miniflux'` (or `AttributeError` once the file exists but functions don't).

- [ ] **Step 3: Write minimal implementation**

Create `miniflux.py`:

```python
#!/usr/bin/env python3
"""Miniflux read-only CLI for agents. Standard library only."""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


class MinifluxError(Exception):
    def __init__(self, message, exit_code=1):
        super().__init__(message)
        self.exit_code = exit_code


def resolve_config(arg_base_url, arg_token, env):
    base_url = arg_base_url or env.get("MINIFLUX_BASE_URL")
    token = arg_token or env.get("MINIFLUX_API_TOKEN")
    if not base_url:
        raise MinifluxError(
            "Missing base URL: set --base-url or MINIFLUX_BASE_URL", exit_code=2
        )
    if not token:
        raise MinifluxError(
            "Missing API token: set --token or MINIFLUX_API_TOKEN", exit_code=2
        )
    return base_url.rstrip("/"), token
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest discover -s tests -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add miniflux.py tests/test_miniflux.py
git commit -m "feat: config resolution and MinifluxError"
```

---

### Task 2: HTTP client `api_request`

**Files:**
- Modify: `miniflux.py`
- Modify: `tests/test_miniflux.py`

**Interfaces:**
- Consumes: `MinifluxError`.
- Produces: `api_request(base_url: str, token: str, method: str, path: str, params: dict|None = None) -> object` — builds `{base_url}/v1/{path}` with urlencoded `params` (`doseq=True`), sets `X-Auth-Token`, returns parsed JSON. Raises `MinifluxError(exit_code=1)` on HTTP error (using Miniflux `error_message` when present), network error, or invalid JSON.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_miniflux.py` (before the `if __name__` block):

```python
import io
import urllib.error
from unittest import mock


class TestApiRequest(unittest.TestCase):
    def _fake_response(self, payload):
        cm = mock.MagicMock()
        cm.__enter__.return_value.read.return_value = json.dumps(payload).encode()
        return cm

    def test_builds_url_sets_header_and_parses_json(self):
        with mock.patch("miniflux.urllib.request.urlopen") as urlopen:
            urlopen.return_value = self._fake_response({"ok": True})
            result = miniflux.api_request("https://x.example", "tok", "GET", "feeds")
        req = urlopen.call_args.args[0]
        self.assertEqual(req.full_url, "https://x.example/v1/feeds")
        self.assertEqual(req.get_header("X-auth-token"), "tok")
        self.assertEqual(result, {"ok": True})

    def test_encodes_params_with_doseq(self):
        with mock.patch("miniflux.urllib.request.urlopen") as urlopen:
            urlopen.return_value = self._fake_response([])
            miniflux.api_request(
                "https://x.example", "tok", "GET", "entries",
                {"status": ["unread", "read"], "limit": 5},
            )
        url = urlopen.call_args.args[0].full_url
        self.assertIn("status=unread", url)
        self.assertIn("status=read", url)
        self.assertIn("limit=5", url)

    def test_http_error_uses_error_message_and_exits_1(self):
        err = urllib.error.HTTPError(
            "u", 403, "Forbidden", {},
            io.BytesIO(json.dumps({"error_message": "Access Unauthorized"}).encode()),
        )
        with mock.patch("miniflux.urllib.request.urlopen", side_effect=err):
            with self.assertRaises(miniflux.MinifluxError) as ctx:
                miniflux.api_request("https://x.example", "tok", "GET", "feeds")
        self.assertEqual(ctx.exception.exit_code, 1)
        self.assertIn("Access Unauthorized", str(ctx.exception))

    def test_network_error_exits_1(self):
        with mock.patch(
            "miniflux.urllib.request.urlopen",
            side_effect=urllib.error.URLError("refused"),
        ):
            with self.assertRaises(miniflux.MinifluxError) as ctx:
                miniflux.api_request("https://x.example", "tok", "GET", "feeds")
        self.assertEqual(ctx.exception.exit_code, 1)

    def test_invalid_json_exits_1(self):
        cm = mock.MagicMock()
        cm.__enter__.return_value.read.return_value = b"not json"
        with mock.patch("miniflux.urllib.request.urlopen", return_value=cm):
            with self.assertRaises(miniflux.MinifluxError) as ctx:
                miniflux.api_request("https://x.example", "tok", "GET", "feeds")
        self.assertEqual(ctx.exception.exit_code, 1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest discover -s tests -v`
Expected: FAIL — `AttributeError: module 'miniflux' has no attribute 'api_request'`.

- [ ] **Step 3: Write minimal implementation**

Append to `miniflux.py` (after `resolve_config`):

```python
def api_request(base_url, token, method, path, params=None):
    url = "{}/v1/{}".format(base_url, path)
    if params:
        url = "{}?{}".format(url, urllib.parse.urlencode(params, doseq=True))
    req = urllib.request.Request(url, method=method)
    req.add_header("X-Auth-Token", token)
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read()
    except urllib.error.HTTPError as exc:
        message = exc.read().decode("utf-8", "replace")
        try:
            message = json.loads(message).get("error_message", message)
        except (ValueError, AttributeError):
            pass
        raise MinifluxError("API error {}: {}".format(exc.code, message), exit_code=1)
    except urllib.error.URLError as exc:
        raise MinifluxError("Network error: {}".format(exc.reason), exit_code=1)
    try:
        return json.loads(body)
    except ValueError:
        raise MinifluxError("Invalid JSON response from server", exit_code=1)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest discover -s tests -v`
Expected: PASS (10 tests).

- [ ] **Step 5: Commit**

```bash
git add miniflux.py tests/test_miniflux.py
git commit -m "feat: api_request HTTP helper with error mapping"
```

---

### Task 3: `strip_content` + `cmd_entries`

**Files:**
- Modify: `miniflux.py`
- Modify: `tests/test_miniflux.py`

**Interfaces:**
- Consumes: nothing (handler receives injected `call`).
- Produces:
  - `strip_content(entry: dict) -> dict` — returns a new dict without the `content` key; does not mutate input.
  - `cmd_entries(args, call) -> object` — builds params from `args` (attrs: `limit`, `offset`, `status` list|None, `order`, `direction`, `category` int|None, `feed` int|None, `search`, `starred` bool); targets `feeds/{feed}/entries` when `feed` is set else `entries`; calls `call("GET", path, params)`; strips `content` from each item in `result["entries"]` when present. `call` signature: `call(method, path, params=None)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_miniflux.py`:

```python
class TestStripContent(unittest.TestCase):
    def test_removes_content_key_only(self):
        entry = {"id": 1, "title": "t", "content": "<p>big</p>"}
        out = miniflux.strip_content(entry)
        self.assertEqual(out, {"id": 1, "title": "t"})

    def test_does_not_mutate_input(self):
        entry = {"id": 1, "content": "x"}
        miniflux.strip_content(entry)
        self.assertIn("content", entry)


class _Args:
    def __init__(self, **kw):
        defaults = dict(
            limit=20, offset=0, status=None, order="published_at",
            direction="desc", category=None, feed=None, search=None, starred=False,
        )
        defaults.update(kw)
        self.__dict__.update(defaults)


class TestCmdEntries(unittest.TestCase):
    def test_default_path_and_strips_content(self):
        captured = {}

        def call(method, path, params=None):
            captured["method"] = method
            captured["path"] = path
            captured["params"] = params
            return {"total": 1, "entries": [{"id": 9, "content": "big"}]}

        result = miniflux.cmd_entries(_Args(), call)
        self.assertEqual(captured["path"], "entries")
        self.assertEqual(captured["params"]["limit"], 20)
        self.assertEqual(captured["params"]["order"], "published_at")
        self.assertEqual(captured["params"]["direction"], "desc")
        self.assertNotIn("content", result["entries"][0])

    def test_feed_filter_changes_path(self):
        def call(method, path, params=None):
            return {"total": 0, "entries": []}

        captured = {}

        def capture(method, path, params=None):
            captured["path"] = path
            return {"total": 0, "entries": []}

        miniflux.cmd_entries(_Args(feed=7), capture)
        self.assertEqual(captured["path"], "feeds/7/entries")

    def test_status_list_and_starred_passed_through(self):
        captured = {}

        def call(method, path, params=None):
            captured["params"] = params
            return {"total": 0, "entries": []}

        miniflux.cmd_entries(_Args(status=["unread", "read"], starred=True), call)
        self.assertEqual(captured["params"]["status"], ["unread", "read"])
        self.assertEqual(captured["params"]["starred"], "true")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest discover -s tests -v`
Expected: FAIL — `AttributeError: module 'miniflux' has no attribute 'strip_content'`.

- [ ] **Step 3: Write minimal implementation**

Append to `miniflux.py`:

```python
def strip_content(entry):
    return {k: v for k, v in entry.items() if k != "content"}


def cmd_entries(args, call):
    params = {"limit": args.limit, "offset": args.offset}
    if args.status:
        params["status"] = args.status
    if args.order:
        params["order"] = args.order
    if args.direction:
        params["direction"] = args.direction
    if args.category is not None:
        params["category_id"] = args.category
    if args.search:
        params["search"] = args.search
    if args.starred:
        params["starred"] = "true"
    if args.feed is not None:
        path = "feeds/{}/entries".format(args.feed)
    else:
        path = "entries"
    result = call("GET", path, params)
    if isinstance(result, dict) and "entries" in result:
        result["entries"] = [strip_content(e) for e in result["entries"]]
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest discover -s tests -v`
Expected: PASS (15 tests).

- [ ] **Step 5: Commit**

```bash
git add miniflux.py tests/test_miniflux.py
git commit -m "feat: strip_content and entries command handler"
```

---

### Task 4: `cmd_entry`, `cmd_feeds`, `cmd_categories`

**Files:**
- Modify: `miniflux.py`
- Modify: `tests/test_miniflux.py`

**Interfaces:**
- Consumes: injected `call(method, path, params=None)`.
- Produces:
  - `cmd_entry(args, call) -> object` — `args.id: int`; returns `call("GET", "entries/{id}")` unchanged (content kept).
  - `cmd_feeds(args, call) -> object` — returns `call("GET", "feeds")`.
  - `cmd_categories(args, call) -> object` — `args.counts: bool`; returns `call("GET", "categories", {"counts": "true"})` when counts else `call("GET", "categories", None)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_miniflux.py`:

```python
class TestOtherCommands(unittest.TestCase):
    def test_cmd_entry_keeps_content(self):
        captured = {}

        def call(method, path, params=None):
            captured["path"] = path
            return {"id": 42, "content": "<p>full</p>"}

        result = miniflux.cmd_entry(_Args2(id=42), call)
        self.assertEqual(captured["path"], "entries/42")
        self.assertEqual(result["content"], "<p>full</p>")

    def test_cmd_feeds(self):
        def call(method, path, params=None):
            self.assertEqual(path, "feeds")
            return [{"id": 1}]

        self.assertEqual(miniflux.cmd_feeds(_Args2(), call), [{"id": 1}])

    def test_cmd_categories_without_counts(self):
        captured = {}

        def call(method, path, params=None):
            captured["params"] = params
            return [{"id": 1}]

        miniflux.cmd_categories(_Args2(counts=False), call)
        self.assertIsNone(captured["params"])

    def test_cmd_categories_with_counts(self):
        captured = {}

        def call(method, path, params=None):
            captured["params"] = params
            return [{"id": 1}]

        miniflux.cmd_categories(_Args2(counts=True), call)
        self.assertEqual(captured["params"], {"counts": "true"})


class _Args2:
    def __init__(self, **kw):
        self.__dict__.update(kw)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest discover -s tests -v`
Expected: FAIL — `AttributeError: module 'miniflux' has no attribute 'cmd_entry'`.

- [ ] **Step 3: Write minimal implementation**

Append to `miniflux.py`:

```python
def cmd_entry(args, call):
    return call("GET", "entries/{}".format(args.id))


def cmd_feeds(args, call):
    return call("GET", "feeds")


def cmd_categories(args, call):
    params = {"counts": "true"} if args.counts else None
    return call("GET", "categories", params)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest discover -s tests -v`
Expected: PASS (19 tests).

- [ ] **Step 5: Commit**

```bash
git add miniflux.py tests/test_miniflux.py
git commit -m "feat: entry, feeds, categories command handlers"
```

---

### Task 5: `build_parser` + `main` dispatch

**Files:**
- Modify: `miniflux.py`
- Modify: `tests/test_miniflux.py`

**Interfaces:**
- Consumes: all `cmd_*` handlers, `resolve_config`, `api_request`, `MinifluxError`.
- Produces:
  - `build_parser() -> argparse.ArgumentParser` with subcommands `entries`, `entry`, `feeds`, `categories` and the flags from the spec; each subparser sets `func` to its handler.
  - `main(argv=None) -> int` — parses args, resolves config from `os.environ`, builds `call` bound to `api_request`, runs `args.func(args, call)`, prints `json.dumps(result, indent=2)` to stdout, returns `0`; on `MinifluxError` prints message to stderr and returns `.exit_code`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_miniflux.py`:

```python
class TestMain(unittest.TestCase):
    def test_feeds_prints_json_and_returns_0(self):
        env = {"MINIFLUX_BASE_URL": "https://x.example", "MINIFLUX_API_TOKEN": "t"}
        out = io.StringIO()
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch("miniflux.api_request", return_value=[{"id": 1}]), \
                mock.patch("sys.stdout", out):
            code = miniflux.main(["feeds"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue()), [{"id": 1}])

    def test_entries_strips_content_end_to_end(self):
        env = {"MINIFLUX_BASE_URL": "https://x.example", "MINIFLUX_API_TOKEN": "t"}
        payload = {"total": 1, "entries": [{"id": 5, "content": "big"}]}
        out = io.StringIO()
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch("miniflux.api_request", return_value=payload), \
                mock.patch("sys.stdout", out):
            code = miniflux.main(["entries", "--limit", "1"])
        self.assertEqual(code, 0)
        self.assertNotIn("content", json.loads(out.getvalue())["entries"][0])

    def test_missing_config_returns_2_and_writes_stderr(self):
        err = io.StringIO()
        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch("sys.stderr", err):
            code = miniflux.main(["feeds"])
        self.assertEqual(code, 2)
        self.assertTrue(err.getvalue().strip())

    def test_api_error_returns_1(self):
        env = {"MINIFLUX_BASE_URL": "https://x.example", "MINIFLUX_API_TOKEN": "t"}
        err = io.StringIO()
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch("miniflux.api_request",
                           side_effect=miniflux.MinifluxError("boom", exit_code=1)), \
                mock.patch("sys.stderr", err):
            code = miniflux.main(["feeds"])
        self.assertEqual(code, 1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest discover -s tests -v`
Expected: FAIL — `AttributeError: module 'miniflux' has no attribute 'main'`.

- [ ] **Step 3: Write minimal implementation**

Append to `miniflux.py`:

```python
def build_parser():
    parser = argparse.ArgumentParser(
        prog="miniflux", description="Miniflux read-only CLI for agents"
    )
    parser.add_argument("--base-url", help="Miniflux base URL (or MINIFLUX_BASE_URL)")
    parser.add_argument("--token", help="API token (or MINIFLUX_API_TOKEN)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_entries = sub.add_parser("entries", help="List recent entries (content stripped)")
    p_entries.add_argument("--limit", type=int, default=20)
    p_entries.add_argument("--offset", type=int, default=0)
    p_entries.add_argument(
        "--status", action="append", choices=["unread", "read", "removed"]
    )
    p_entries.add_argument("--order", default="published_at")
    p_entries.add_argument("--direction", choices=["asc", "desc"], default="desc")
    p_entries.add_argument("--category", type=int)
    p_entries.add_argument("--feed", type=int)
    p_entries.add_argument("--search")
    p_entries.add_argument("--starred", action="store_true")
    p_entries.set_defaults(func=cmd_entries)

    p_entry = sub.add_parser("entry", help="Get one entry by id (full content)")
    p_entry.add_argument("id", type=int)
    p_entry.set_defaults(func=cmd_entry)

    p_feeds = sub.add_parser("feeds", help="List all feeds")
    p_feeds.set_defaults(func=cmd_feeds)

    p_categories = sub.add_parser("categories", help="List categories")
    p_categories.add_argument(
        "--counts", action="store_true", help="Include unread/total counts"
    )
    p_categories.set_defaults(func=cmd_categories)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        base_url, token = resolve_config(args.base_url, args.token, os.environ)

        def call(method, path, params=None):
            return api_request(base_url, token, method, path, params)

        result = args.func(args, call)
    except MinifluxError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest discover -s tests -v`
Expected: PASS (23 tests).

- [ ] **Step 5: Commit**

```bash
git add miniflux.py tests/test_miniflux.py
git commit -m "feat: argparse parser and main dispatch"
```

---

### Task 6: README + live verification

**Files:**
- Create: `README.md`

**Interfaces:**
- Consumes: the finished CLI.
- Produces: usage docs. No code.

- [ ] **Step 1: Write `README.md`**

```markdown
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
```

- [ ] **Step 2: Live verification against a real instance**

With `MINIFLUX_BASE_URL` and `MINIFLUX_API_TOKEN` exported, run and confirm each:

```bash
python miniflux.py feeds | head        # JSON array of feeds
python miniflux.py categories --counts # categories with counts
python miniflux.py entries --limit 3   # 3 entries, NO "content" key
python miniflux.py entry <id>          # id from above, HAS "content"
env -u MINIFLUX_API_TOKEN python miniflux.py feeds; echo "exit=$?"  # exit=2
```

Expected: first four emit JSON to stdout; the last prints a config error to stderr and `exit=2`.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add README and verification steps"
```

---

## Self-Review Notes

- **Spec coverage:** config resolution (T1), HTTP + error mapping + exit codes (T2, T5), `entries`/strip-content/`--feed` (T3), `entry`/`feeds`/`categories --counts` (T4), argparse + JSON stdout (T5), manual verification + docs (T6). All spec sections mapped.
- **Constraints:** stdlib-only honored (runtime + `unittest` tests); JSON-stdout/stderr-only and exit codes covered by T5 tests.
- **Type consistency:** `call(method, path, params=None)` signature identical across T3–T5; `cmd_*` all `(args, call) -> object`; `MinifluxError.exit_code` used consistently.

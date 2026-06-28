# New Miniflux CLI Commands Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add five drill-down/triage read commands plus two mutating commands (`mark`, `catch-up`) to the Miniflux agent CLI.

**Architecture:** Extend the existing flat, dependency-injected `miniflux.py`. Add request-body support to the single network boundary `api_request`, then add `cmd_*` handlers (each taking a `call` callable) and wire them into `build_parser`. Keep the "scan cheap, then drill" asymmetry: list commands strip `content`, single-entry/fetch commands keep it.

**Tech Stack:** Python 3 standard library only (`argparse`, `json`, `urllib`). Tests use `unittest` + `unittest.mock`. No pytest, no third-party deps.

## Global Constraints

- **Standard library only.** No third-party imports in `miniflux.py` or tests. Verbatim from spec/CLAUDE.md.
- **`.format()` strings, not f-strings** — broad-runtime portability; match existing style.
- **Output contract:** stdout is JSON on success; errors to stderr. Exit codes: `1` = API/network/JSON failure, `2` = usage/missing config.
- **Test seams:** inject a fake `call` for command-logic tests; mock `miniflux.urllib.request.urlopen` for `api_request` plumbing. Never hit a live server.
- **Five parallel surfaces stay in sync:** `miniflux-cli/scripts/miniflux.py`, `miniflux-cli/SKILL.md`, `README.md`, `tests/test_miniflux.py`, `miniflux-cli/evals/evals.json`.
- **Run the suite with:** `python3 -m unittest discover -s tests -v`

---

### Task 1: Request-body support + empty-response handling in `api_request`

**Files:**
- Modify: `miniflux-cli/scripts/miniflux.py` (`api_request`, the `call` closure in `main`)
- Test: `tests/test_miniflux.py` (class `TestApiRequest`)

**Interfaces:**
- Consumes: nothing new.
- Produces: `api_request(base_url, token, method, path, params=None, data=None)` — when `data` is not `None`, sends `json.dumps(data)` UTF-8 bytes as the request body with header `Content-Type: application/json`; returns `None` when the response body is empty (e.g. HTTP 204); otherwise parses JSON as before. The `call` closure in `main` becomes `call(method, path, params=None, data=None)`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_miniflux.py` inside class `TestApiRequest`. Add an empty-body helper and two tests:

```python
    def _fake_empty_response(self):
        cm = mock.MagicMock()
        cm.__enter__.return_value.read.return_value = b""
        return cm

    def test_put_sends_json_body_and_content_type(self):
        with mock.patch("miniflux.urllib.request.urlopen") as urlopen:
            urlopen.return_value = self._fake_empty_response()
            result = miniflux.api_request(
                "https://x.example", "tok", "PUT", "entries",
                data={"entry_ids": [1, 2], "status": "read"},
            )
        req = urlopen.call_args.args[0]
        self.assertEqual(req.get_method(), "PUT")
        self.assertEqual(
            req.data, json.dumps({"entry_ids": [1, 2], "status": "read"}).encode("utf-8")
        )
        self.assertEqual(req.get_header("Content-type"), "application/json")
        self.assertIsNone(result)

    def test_empty_body_returns_none(self):
        with mock.patch("miniflux.urllib.request.urlopen") as urlopen:
            urlopen.return_value = self._fake_empty_response()
            result = miniflux.api_request("https://x.example", "tok", "GET", "feeds")
        self.assertIsNone(result)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_miniflux.TestApiRequest -v`
Expected: FAIL — `test_put_sends_json_body_and_content_type` errors on the unexpected `data=` kwarg / missing body; `test_empty_body_returns_none` fails with "Invalid JSON response from server".

- [ ] **Step 3: Implement body + empty-response handling**

Replace `api_request` in `miniflux-cli/scripts/miniflux.py` with:

```python
def api_request(base_url, token, method, path, params=None, data=None):
    url = "{}/v1/{}".format(base_url, path)
    if params:
        url = "{}?{}".format(url, urllib.parse.urlencode(params, doseq=True))
    body_bytes = None
    if data is not None:
        body_bytes = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body_bytes, method=method)
    req.add_header("X-Auth-Token", token)
    if body_bytes is not None:
        req.add_header("Content-Type", "application/json")
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
    if not body:
        return None
    try:
        return json.loads(body)
    except ValueError:
        raise MinifluxError("Invalid JSON response from server", exit_code=1)
```

Then update the `call` closure inside `main` to forward `data`:

```python
        def call(method, path, params=None, data=None):
            return api_request(base_url, token, method, path, params, data)
```

- [ ] **Step 4: Run the full suite to verify pass (no regressions)**

Run: `python3 -m unittest discover -s tests -v`
Expected: PASS — new tests pass and all existing `TestApiRequest` GET tests still pass.

- [ ] **Step 5: Commit**

```bash
git add miniflux-cli/scripts/miniflux.py tests/test_miniflux.py
git commit -m "feat: support JSON request bodies and empty responses in api_request"
```

---

### Task 2: Read drill-down commands — `fetch-content`, `counters`, `feed`

**Files:**
- Modify: `miniflux-cli/scripts/miniflux.py` (new handlers + `build_parser`)
- Test: `tests/test_miniflux.py` (new class `TestReadDrillCommands`)

**Interfaces:**
- Consumes: the `call` seam.
- Produces:
  - `cmd_fetch_content(args, call)` → `call("GET", "entries/{}/fetch-content".format(args.id))` (args: `.id`)
  - `cmd_counters(args, call)` → `call("GET", "feeds/counters")`
  - `cmd_feed(args, call)` → `call("GET", "feeds/{}".format(args.id))` (args: `.id`)
  - Subcommands `fetch-content <id>`, `counters`, `feed <id>`.

- [ ] **Step 1: Write the failing tests**

Add a new class to `tests/test_miniflux.py` (it reuses the existing `_Args2` helper, which is defined later in the file — that's fine, it's resolved at call time):

```python
class TestReadDrillCommands(unittest.TestCase):
    def test_cmd_fetch_content_path(self):
        captured = {}

        def call(method, path, params=None, data=None):
            captured["method"] = method
            captured["path"] = path
            return {"content": "<p>full</p>"}

        result = miniflux.cmd_fetch_content(_Args2(id=42), call)
        self.assertEqual(captured["method"], "GET")
        self.assertEqual(captured["path"], "entries/42/fetch-content")
        self.assertEqual(result["content"], "<p>full</p>")

    def test_cmd_counters_path(self):
        captured = {}

        def call(method, path, params=None, data=None):
            captured["path"] = path
            return {"unreads": {"1": 3}}

        miniflux.cmd_counters(_Args2(), call)
        self.assertEqual(captured["path"], "feeds/counters")

    def test_cmd_feed_path(self):
        captured = {}

        def call(method, path, params=None, data=None):
            captured["path"] = path
            return {"id": 3}

        miniflux.cmd_feed(_Args2(id=3), call)
        self.assertEqual(captured["path"], "feeds/3")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_miniflux.TestReadDrillCommands -v`
Expected: FAIL — `AttributeError: module 'miniflux' has no attribute 'cmd_fetch_content'`.

- [ ] **Step 3: Implement the handlers**

Add to `miniflux-cli/scripts/miniflux.py` (after `cmd_entry`):

```python
def cmd_fetch_content(args, call):
    return call("GET", "entries/{}/fetch-content".format(args.id))


def cmd_counters(args, call):
    return call("GET", "feeds/counters")


def cmd_feed(args, call):
    return call("GET", "feeds/{}".format(args.id))
```

- [ ] **Step 4: Wire the subcommands**

In `build_parser`, after the existing `p_entry` block, add:

```python
    p_fetch = sub.add_parser(
        "fetch-content", help="Get full scraped article for one entry"
    )
    p_fetch.add_argument("id", type=int)
    p_fetch.set_defaults(func=cmd_fetch_content)

    p_counters = sub.add_parser("counters", help="Unread/read counts per feed")
    p_counters.set_defaults(func=cmd_counters)

    p_feed = sub.add_parser("feed", help="Get one feed by id")
    p_feed.add_argument("id", type=int)
    p_feed.set_defaults(func=cmd_feed)
```

- [ ] **Step 5: Run the full suite to verify pass**

Run: `python3 -m unittest discover -s tests -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add miniflux-cli/scripts/miniflux.py tests/test_miniflux.py
git commit -m "feat: add fetch-content, counters, and feed read commands"
```

---

### Task 3: Extend `feeds` with `--category`

**Files:**
- Modify: `miniflux-cli/scripts/miniflux.py` (`cmd_feeds`, `p_feeds` in `build_parser`)
- Test: `tests/test_miniflux.py` (`TestOtherCommands.test_cmd_feeds`)

**Interfaces:**
- Consumes: the `call` seam.
- Produces: `cmd_feeds(args, call)` now reads `args.category`. When it is not `None`, requests `categories/{id}/feeds`; otherwise `feeds`. The `feeds` subparser gains `--category` (type `int`, default `None`).

- [ ] **Step 1: Replace the existing `test_cmd_feeds` with two tests**

In `tests/test_miniflux.py`, inside `TestOtherCommands`, replace the current `test_cmd_feeds` method with:

```python
    def test_cmd_feeds_all(self):
        def call(method, path, params=None, data=None):
            self.assertEqual(path, "feeds")
            return [{"id": 1}]

        self.assertEqual(miniflux.cmd_feeds(_Args2(category=None), call), [{"id": 1}])

    def test_cmd_feeds_by_category(self):
        captured = {}

        def call(method, path, params=None, data=None):
            captured["path"] = path
            return [{"id": 5}]

        miniflux.cmd_feeds(_Args2(category=4), call)
        self.assertEqual(captured["path"], "categories/4/feeds")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_miniflux.TestOtherCommands -v`
Expected: FAIL — `test_cmd_feeds_by_category` requests `feeds` instead of `categories/4/feeds`.

- [ ] **Step 3: Implement the path switch**

Replace `cmd_feeds` in `miniflux-cli/scripts/miniflux.py` with:

```python
def cmd_feeds(args, call):
    if args.category is not None:
        return call("GET", "categories/{}/feeds".format(args.category))
    return call("GET", "feeds")
```

- [ ] **Step 4: Add the `--category` flag to the `feeds` subparser**

In `build_parser`, replace the `p_feeds` block with:

```python
    p_feeds = sub.add_parser("feeds", help="List all feeds")
    p_feeds.add_argument(
        "--category", type=int, help="List only this category's feeds"
    )
    p_feeds.set_defaults(func=cmd_feeds)
```

- [ ] **Step 5: Run the full suite to verify pass**

Run: `python3 -m unittest discover -s tests -v`
Expected: PASS — including the existing `TestMain.test_feeds_prints_json_and_returns_0` (parser now supplies `category=None`).

- [ ] **Step 6: Commit**

```bash
git add miniflux-cli/scripts/miniflux.py tests/test_miniflux.py
git commit -m "feat: support feeds --category to list a category's feeds"
```

---

### Task 4: `mark <status> <id...>` write command

**Files:**
- Modify: `miniflux-cli/scripts/miniflux.py` (new handler + `build_parser`)
- Test: `tests/test_miniflux.py` (new class `TestCmdMark`, plus a `TestMain` e2e test)

**Interfaces:**
- Consumes: the `call` seam with `data=`.
- Produces: `cmd_mark(args, call)` (args: `.status` one of `read|unread|removed`, `.ids` list of ints) → `call("PUT", "entries", data={"entry_ids": args.ids, "status": args.status})`, then returns the confirmation dict `{"entry_ids": args.ids, "status": args.status}`. Subcommand `mark <status> <id...>`.

- [ ] **Step 1: Write the failing tests**

Add a new class to `tests/test_miniflux.py`:

```python
class TestCmdMark(unittest.TestCase):
    def test_sends_put_with_entry_ids_and_status(self):
        captured = {}

        def call(method, path, params=None, data=None):
            captured["method"] = method
            captured["path"] = path
            captured["data"] = data
            return None

        result = miniflux.cmd_mark(_Args2(status="read", ids=[1, 2]), call)
        self.assertEqual(captured["method"], "PUT")
        self.assertEqual(captured["path"], "entries")
        self.assertEqual(captured["data"], {"entry_ids": [1, 2], "status": "read"})
        self.assertEqual(result, {"entry_ids": [1, 2], "status": "read"})
```

And add an end-to-end test to the existing `TestMain` class:

```python
    def test_mark_prints_confirmation_and_returns_0(self):
        env = {"MINIFLUX_BASE_URL": "https://x.example", "MINIFLUX_API_TOKEN": "t"}
        out = io.StringIO()
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch("miniflux.api_request", return_value=None), \
                mock.patch("sys.stdout", out):
            code = miniflux.main(["mark", "read", "5", "6"])
        self.assertEqual(code, 0)
        self.assertEqual(
            json.loads(out.getvalue()), {"entry_ids": [5, 6], "status": "read"}
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_miniflux.TestCmdMark tests.test_miniflux.TestMain.test_mark_prints_confirmation_and_returns_0 -v`
Expected: FAIL — `cmd_mark` undefined; `main` errors with `invalid choice: 'mark'`.

- [ ] **Step 3: Implement the handler**

Add to `miniflux-cli/scripts/miniflux.py` (after `cmd_categories`):

```python
def cmd_mark(args, call):
    call("PUT", "entries", data={"entry_ids": args.ids, "status": args.status})
    return {"entry_ids": args.ids, "status": args.status}
```

- [ ] **Step 4: Wire the subcommand**

In `build_parser`, after the `p_categories` block, add:

```python
    p_mark = sub.add_parser("mark", help="Mark entries read/unread/removed")
    p_mark.add_argument("status", choices=["read", "unread", "removed"])
    p_mark.add_argument("ids", nargs="+", type=int)
    p_mark.set_defaults(func=cmd_mark)
```

- [ ] **Step 5: Run the full suite to verify pass**

Run: `python3 -m unittest discover -s tests -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add miniflux-cli/scripts/miniflux.py tests/test_miniflux.py
git commit -m "feat: add mark command to set entry status"
```

---

### Task 5: `catch-up` — fetch unread, mark read, return them

**Files:**
- Modify: `miniflux-cli/scripts/miniflux.py` (new handler + `build_parser`)
- Test: `tests/test_miniflux.py` (new class `TestCmdCatchUp`)

**Interfaces:**
- Consumes: the `call` seam (GET then conditional PUT with `data=`); `strip_content`.
- Produces: `cmd_catch_up(args, call)` (args: `.limit`, `.feed`, `.category`). Fetches unread via `GET` (path `feeds/{feed}/entries` when `--feed`, else `entries`; `category_id` param when `--category`; `status=unread`, `limit`), collects ids, and if any, issues `PUT entries {"entry_ids": ids, "status": "read"}` **before returning**. Returns a list of the entries with `content` stripped (empty list when nothing unread, with no PUT). When both `--feed` and `--category` are given, `--feed` wins (path switch). Subcommand `catch-up [--limit N] [--feed ID] [--category ID]` (default `--limit 100`).

- [ ] **Step 1: Write the failing tests**

Add a new class to `tests/test_miniflux.py`. These tests record every `call` invocation in order:

```python
class TestCmdCatchUp(unittest.TestCase):
    def _recorder(self, get_result):
        calls = []

        def call(method, path, params=None, data=None):
            calls.append({"method": method, "path": path, "params": params, "data": data})
            if method == "GET":
                return get_result
            return None

        return calls, call

    def test_marks_unread_read_and_strips_content(self):
        get_result = {"entries": [
            {"id": 1, "content": "a"}, {"id": 2, "content": "b"},
        ]}
        calls, call = self._recorder(get_result)
        result = miniflux.cmd_catch_up(_Args(), call)
        self.assertEqual(calls[0]["method"], "GET")
        self.assertEqual(calls[0]["path"], "entries")
        self.assertEqual(calls[0]["params"]["status"], "unread")
        self.assertEqual(calls[1]["method"], "PUT")
        self.assertEqual(calls[1]["path"], "entries")
        self.assertEqual(calls[1]["data"], {"entry_ids": [1, 2], "status": "read"})
        self.assertEqual(result, [{"id": 1}, {"id": 2}])

    def test_empty_unread_skips_put(self):
        calls, call = self._recorder({"entries": []})
        result = miniflux.cmd_catch_up(_Args(), call)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["method"], "GET")
        self.assertEqual(result, [])

    def test_feed_filter_changes_path(self):
        calls, call = self._recorder({"entries": []})
        miniflux.cmd_catch_up(_Args(feed=7), call)
        self.assertEqual(calls[0]["path"], "feeds/7/entries")

    def test_category_filter_sets_param(self):
        calls, call = self._recorder({"entries": []})
        miniflux.cmd_catch_up(_Args(category=3), call)
        self.assertEqual(calls[0]["path"], "entries")
        self.assertEqual(calls[0]["params"]["category_id"], 3)

    def test_feed_wins_over_category(self):
        calls, call = self._recorder({"entries": []})
        miniflux.cmd_catch_up(_Args(feed=7, category=3), call)
        self.assertEqual(calls[0]["path"], "feeds/7/entries")

    def test_put_failure_propagates_and_does_not_return(self):
        def call(method, path, params=None, data=None):
            if method == "GET":
                return {"entries": [{"id": 1, "content": "a"}]}
            raise miniflux.MinifluxError("boom", exit_code=1)

        with self.assertRaises(miniflux.MinifluxError):
            miniflux.cmd_catch_up(_Args(), call)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_miniflux.TestCmdCatchUp -v`
Expected: FAIL — `AttributeError: module 'miniflux' has no attribute 'cmd_catch_up'`.

- [ ] **Step 3: Implement the handler**

Add to `miniflux-cli/scripts/miniflux.py` (after `cmd_mark`):

```python
def cmd_catch_up(args, call):
    params = {"status": "unread", "limit": args.limit}
    if args.category is not None:
        params["category_id"] = args.category
    if args.feed is not None:
        path = "feeds/{}/entries".format(args.feed)
    else:
        path = "entries"
    result = call("GET", path, params)
    entries = result.get("entries", []) if isinstance(result, dict) else []
    ids = [e["id"] for e in entries]
    if ids:
        call("PUT", "entries", data={"entry_ids": ids, "status": "read"})
    return [strip_content(e) for e in entries]
```

- [ ] **Step 4: Wire the subcommand**

In `build_parser`, after the `p_mark` block, add:

```python
    p_catch = sub.add_parser(
        "catch-up", help="Fetch unread entries and mark them read"
    )
    p_catch.add_argument("--limit", type=int, default=100)
    p_catch.add_argument("--feed", type=int)
    p_catch.add_argument("--category", type=int)
    p_catch.set_defaults(func=cmd_catch_up)
```

- [ ] **Step 5: Run the full suite to verify pass**

Run: `python3 -m unittest discover -s tests -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add miniflux-cli/scripts/miniflux.py tests/test_miniflux.py
git commit -m "feat: add catch-up command to drain and mark unread entries"
```

---

### Task 6: Sync agent/human docs and evals

**Files:**
- Modify: `miniflux-cli/SKILL.md`, `README.md`, `miniflux-cli/evals/evals.json`

**Interfaces:**
- Consumes: the finished command surface from Tasks 1–5.
- Produces: documentation and evals matching the implemented behavior. No code; this task's "test" is a clean full-suite run plus a manual `--help` sanity check.

- [ ] **Step 1: Update `SKILL.md` frontmatter and intro (drop the read-only promise)**

In `miniflux-cli/SKILL.md`:

Change the frontmatter `description` first line from `read-only miniflux.py CLI` to `miniflux.py CLI`, and extend the trigger examples to include catch-up phrasing, e.g. add `"catch me up and mark as read"`.

Replace the intro paragraph (lines ~17–22, the "**read-only** CLI ... always safe to run" sentence) with:

```markdown
This skill bundles `scripts/miniflux.py` — a zero-dependency CLI for browsing a
Miniflux RSS instance. Run it as `python3 scripts/miniflux.py <command>` (path
relative to this skill's directory; from the repo root that's
`python3 miniflux-cli/scripts/miniflux.py`). Results are pretty-printed JSON on
**stdout**; errors go to **stderr**. Most commands only read, but `mark` and
`catch-up` **change entry state on the server** — see "Commands that change state"
below.
```

- [ ] **Step 2: Update the `SKILL.md` Commands block**

Replace the fenced command list with:

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

And extend the bullet descriptions below it with these entries:

```markdown
- **`fetch-content <id>`** → `{"content": ...}` with the **full scraped original
  article**. Use when an `entry`'s `content` is truncated or empty. Third drill
  level after `entries` (no content) and `entry` (feed content).
- **`feeds [--category ID]`** → every feed, or only that category's feeds.
- **`feed <id>`** → one feed's details.
- **`counters`** → unread/read counts per feed id. Cheap triage to find which
  feeds have new items without paging entries.
```

- [ ] **Step 3: Add a "Commands that change state" section to `SKILL.md`**

Insert after the "scan cheap, then drill" section:

```markdown
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
```

- [ ] **Step 4: Update `README.md`**

Replace the Commands block in `README.md` with:

```
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
```

And replace the line `` `entries` omits each entry's `content`; use `entry <id>` for the full article. `` with:

```markdown
`entries` omits each entry's `content`; use `entry <id>` (feed content) or
`fetch-content <id>` (full scraped article) to read one. `mark` and `catch-up`
change entry state on the server; all other commands only read.
```

Also update the one-line summary near the top: change "lets an agent read a Miniflux instance" to "lets an agent read and triage a Miniflux instance".

- [ ] **Step 5: Add a `catch-up` eval**

In `miniflux-cli/evals/evals.json`, append this object to the `evals` array (after id 3):

```json
    {
      "id": 4,
      "prompt": "Catch me up on my unread articles and clear them out as you go.",
      "expected_output": "Triggers the skill; runs `catch-up` (optionally scoped with --feed/--category) which fetches unread entries AND marks them read in one step, then summarizes. Recognizes catch-up mutates server state, unlike plain `entries --status unread`.",
      "files": []
    }
```

- [ ] **Step 6: Verify suite passes and commands parse**

Run: `python3 -m unittest discover -s tests -v`
Expected: PASS (no code changed, but confirms nothing drifted).

Run: `python3 miniflux-cli/scripts/miniflux.py --help`
Expected: usage lists `entries`, `entry`, `fetch-content`, `feeds`, `feed`, `counters`, `categories`, `mark`, `catch-up`.

Run: `python3 -c "import json; json.load(open('miniflux-cli/evals/evals.json'))"`
Expected: no output (valid JSON).

- [ ] **Step 7: Commit**

```bash
git add miniflux-cli/SKILL.md README.md miniflux-cli/evals/evals.json
git commit -m "docs: document new read/write commands; drop read-only promise"
```

---

## Self-Review

**Spec coverage:**
- `fetch-content`, `counters`, `feed`, `feeds --category` → Tasks 2–3. ✓
- `mark <status> <id...>` (PUT body, 204→confirmation echo) → Tasks 1, 4. ✓
- `catch-up` (mark-first, empty→`[]`/no PUT, `--feed`/`--category`/`--limit`, feed precedence) → Task 5. ✓
- `api_request` `data` param + empty-body handling → Task 1. ✓
- Output/exit-code contract preserved (mark echoes dict, catch-up returns list) → Tasks 4–5. ✓
- Five-surface sync (impl, SKILL.md, README, tests, evals) → all tasks + Task 6. ✓
- "Read-only / always safe to run" promise rewritten → Task 6 Steps 1, 3. ✓

**Placeholder scan:** No TBD/TODO; every code and test step shows full content. ✓

**Type consistency:** `call(method, path, params=None, data=None)` used uniformly from Task 1 onward; fakes in Tasks 2–5 match. `cmd_catch_up` returns `list`, `cmd_mark` returns `dict`, read handlers return the API payload — consistent with the tests and `main`'s `json.dumps`. `_Args` (entries-style defaults: `limit`/`feed`/`category`) used for `catch-up`; `_Args2` (bare) used for `id`/`status`/`ids`/`category`-only cases — matches their definitions in the test file. ✓

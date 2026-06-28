import io
import json
import os
import socket
import sys
import unittest
import urllib.error
from unittest import mock

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO_ROOT, "miniflux-cli", "scripts"))
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

    def test_http_error_non_json_body_falls_back_to_raw_text(self):
        err = urllib.error.HTTPError(
            "u", 500, "Internal Server Error", {},
            io.BytesIO(b"Internal Server Error"),
        )
        with mock.patch("miniflux.urllib.request.urlopen", side_effect=err):
            with self.assertRaises(miniflux.MinifluxError) as ctx:
                miniflux.api_request("https://x.example", "tok", "GET", "feeds")
        self.assertEqual(ctx.exception.exit_code, 1)
        self.assertIn("Internal Server Error", str(ctx.exception))

    def test_network_error_exits_1(self):
        with mock.patch(
            "miniflux.urllib.request.urlopen",
            side_effect=urllib.error.URLError("refused"),
        ):
            with self.assertRaises(miniflux.MinifluxError) as ctx:
                miniflux.api_request("https://x.example", "tok", "GET", "feeds")
        self.assertEqual(ctx.exception.exit_code, 1)

    def test_timeout_exits_1(self):
        with mock.patch(
            "miniflux.urllib.request.urlopen",
            side_effect=socket.timeout("timed out"),
        ):
            with self.assertRaises(miniflux.MinifluxError) as ctx:
                miniflux.api_request("https://x.example", "tok", "GET", "feeds")
        self.assertEqual(ctx.exception.exit_code, 1)
        self.assertIn("timeout", str(ctx.exception).lower())

    def test_urlerror_wrapping_timeout_reports_timeout(self):
        with mock.patch(
            "miniflux.urllib.request.urlopen",
            side_effect=urllib.error.URLError(socket.timeout("timed out")),
        ):
            with self.assertRaises(miniflux.MinifluxError) as ctx:
                miniflux.api_request("https://x.example", "tok", "GET", "feeds")
        self.assertEqual(ctx.exception.exit_code, 1)
        self.assertIn("timeout", str(ctx.exception).lower())

    def test_passes_timeout_to_urlopen(self):
        with mock.patch("miniflux.urllib.request.urlopen") as urlopen:
            urlopen.return_value = self._fake_response({"ok": True})
            miniflux.api_request("https://x.example", "tok", "GET", "feeds")
        self.assertEqual(
            urlopen.call_args.kwargs.get("timeout"), miniflux.REQUEST_TIMEOUT
        )

    def test_invalid_json_exits_1(self):
        cm = mock.MagicMock()
        cm.__enter__.return_value.read.return_value = b"not json"
        with mock.patch("miniflux.urllib.request.urlopen", return_value=cm):
            with self.assertRaises(miniflux.MinifluxError) as ctx:
                miniflux.api_request("https://x.example", "tok", "GET", "feeds")
        self.assertEqual(ctx.exception.exit_code, 1)

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


class TestOtherCommands(unittest.TestCase):
    def test_cmd_entry_keeps_content(self):
        captured = {}

        def call(method, path, params=None):
            captured["path"] = path
            return {"id": 42, "content": "<p>full</p>"}

        result = miniflux.cmd_entry(_Args2(id=42), call)
        self.assertEqual(captured["path"], "entries/42")
        self.assertEqual(result["content"], "<p>full</p>")

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


class TestCmdCatchUp(unittest.TestCase):
    def _recorder(self, get_result):
        calls = []

        def call(method, path, params=None, data=None):
            calls.append(
                {"method": method, "path": path, "params": params, "data": data}
            )
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


class _Args2:
    def __init__(self, **kw):
        self.__dict__.update(kw)


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


if __name__ == "__main__":
    unittest.main()

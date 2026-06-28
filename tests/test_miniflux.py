import io
import json
import os
import sys
import unittest
import urllib.error
from unittest import mock

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


if __name__ == "__main__":
    unittest.main()

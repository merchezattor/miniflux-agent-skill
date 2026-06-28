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

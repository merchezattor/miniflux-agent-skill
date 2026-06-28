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


def cmd_entry(args, call):
    return call("GET", "entries/{}".format(args.id))


def cmd_feeds(args, call):
    return call("GET", "feeds")


def cmd_categories(args, call):
    params = {"counts": "true"} if args.counts else None
    return call("GET", "categories", params)


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

        def call(method, path, params=None, data=None):
            return api_request(base_url, token, method, path, params, data)

        result = args.func(args, call)
    except MinifluxError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

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

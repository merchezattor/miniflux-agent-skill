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

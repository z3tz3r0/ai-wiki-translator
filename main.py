"""Backward-compatible entry point that proxies to the CLI."""

from __future__ import annotations

from app.cli import main as cli_main

if __name__ == "__main__":
    cli_main()

"""Minimal .env loader so API keys don't have to be exported in the shell.

Reads KEY=VALUE lines from a .env file (gitignored) into os.environ without
overriding anything already set in the environment.
"""
from __future__ import annotations

import os
from pathlib import Path


def load_env(path: str = ".env") -> None:
    p = Path(path)
    if not p.exists():
        return
    for raw in p.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        # An already-exported env var wins over the file.
        os.environ.setdefault(key, val)

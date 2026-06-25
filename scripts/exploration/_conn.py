"""Shared connection helper for the ad-hoc exploration scripts.

Credentials are read from environment variables — never hardcode them here.
These scripts were used to inspect internal MariaDB servers (ad_service,
kbme_*, matgrade, ...) and are kept only for reference.

Required environment variables:

    EXPLORE_DB_HOST       (default: localhost)
    EXPLORE_DB_PORT       (default: 3306)
    EXPLORE_DB_USER       (required)
    EXPLORE_DB_PASSWORD   (required)

For the multi-server scripts, set:

    EXPLORE_SERVERS = "host:port:user,host:port:user,..."

The password for every server in EXPLORE_SERVERS is taken from
EXPLORE_DB_PASSWORD. Put these in a local, git-ignored .env and load it
(e.g. `set -a; . ./.env; set +a`) before running a script.
"""

from __future__ import annotations

import os


def _require(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None or value == "":
        raise SystemExit(
            f"Missing required environment variable: {name}. "
            "See scripts/exploration/README.md for setup."
        )
    return value


def conn_kwargs(*, db: str | None = None) -> dict:
    """Build asyncmy.connect(**kwargs) from the environment."""
    kwargs: dict = {
        "host": _require("EXPLORE_DB_HOST", "localhost"),
        "port": int(_require("EXPLORE_DB_PORT", "3306")),
        "user": _require("EXPLORE_DB_USER"),
        "password": _require("EXPLORE_DB_PASSWORD"),
    }
    if db:
        kwargs["db"] = db
    return kwargs


def servers() -> list[tuple[str, int, str, str]]:
    """Parse EXPLORE_SERVERS='host:port:user,...' into connection tuples."""
    raw = _require("EXPLORE_SERVERS")
    password = _require("EXPLORE_DB_PASSWORD")
    parsed: list[tuple[str, int, str, str]] = []
    for entry in (e.strip() for e in raw.split(",")):
        if not entry:
            continue
        host, port, user = entry.split(":")
        parsed.append((host, int(port), user, password))
    return parsed

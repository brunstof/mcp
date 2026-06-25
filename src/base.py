# base.py
"""Shared state and construction for the MariaDB MCP server.

`ServerBase` owns the single ``__init__`` and declares every instance attribute
used across the pool / query / tools mixins. The mixins inherit from this base
(directly or transitively) so that type checking sees a consistent ``self``
surface without duplicated stubs or ``# type: ignore`` comments.
"""

import asyncio
import time

import asyncmy
from fastmcp import FastMCP

from config import MCP_READ_ONLY, logger


class ServerBase:
    """Holds the connection pools, metrics, and configuration-derived state.

    This class contains no database logic; the behavior lives in the mixins
    (`PoolMixin`, `QueryMixin`, `StandardToolsMixin`, `VectorToolsMixin`) that
    inherit from it. The instance attributes set here give every mixin a single
    source of truth for ``self``. (`PoolMixin` re-declares the two attributes it
    reassigns — ``pool`` and ``_embedding_semaphore`` — locally, to keep type
    checking free of cross-module deferral.)
    """

    def __init__(self, server_name: str = "MariaDB_Server") -> None:
        self.mcp = FastMCP(server_name)
        self.pool: asyncmy.Pool | None = None
        self.pools: dict[str, asyncmy.Pool] = {}  # Multiple pools by connection name
        self.autocommit = not MCP_READ_ONLY
        self.is_read_only = MCP_READ_ONLY
        self._current_db_cache: dict[int, str] = {}  # Cache database context per connection
        # Semaphore for rate limiting embedding API calls (set during pool init)
        self._embedding_semaphore: asyncio.Semaphore | None = None
        # Metrics tracking
        self._metrics: dict[str, int] = {
            "queries_executed": 0,
            "query_errors": 0,
            "total_query_time_ms": 0,
            "embeddings_generated": 0,
            "pool_acquisitions": 0,
        }
        self._start_time = time.time()
        logger.info(f"Initializing {server_name}...")
        if self.is_read_only:
            logger.warning("Server running in READ-ONLY mode. Write operations are disabled.")

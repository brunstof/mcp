# db_pool.py
"""Connection-pool lifecycle for the MariaDB MCP server.

`PoolMixin` manages creation, warmup, and graceful shutdown of one or more
`asyncmy` connection pools, plus initialization of the embedding rate-limiter
semaphore. It carries no query logic.
"""

import asyncio

import asyncmy
from asyncmy.errors import Error as AsyncMyError

from base import ServerBase
from config import (
    DB_CHARSET,
    DB_CHARSETS,
    DB_CONNECT_TIMEOUT,
    DB_HOST,
    DB_HOSTS,
    DB_NAME,
    DB_NAMES,
    DB_PASSWORD,
    DB_PASSWORDS,
    DB_PORT,
    DB_PORTS,
    DB_USER,
    DB_USERS,
    EMBEDDING_MAX_CONCURRENT,
    EMBEDDING_PROVIDER,
    MCP_MAX_POOL_SIZE,
    logger,
)


class PoolMixin(ServerBase):
    """Connection-pool creation, warmup, and teardown."""

    # Re-declared from ServerBase: these are the attributes this mixin reassigns,
    # so declaring their type locally keeps mypy from a cross-module [has-type]
    # deferral when it analyzes the reassignment + read together.
    pool: asyncmy.Pool | None
    _embedding_semaphore: asyncio.Semaphore | None

    def _init_embedding_semaphore(self) -> None:
        """Initialize the embedding rate-limiter semaphore if not already set."""
        if EMBEDDING_PROVIDER is not None and self._embedding_semaphore is None:
            self._embedding_semaphore = asyncio.Semaphore(EMBEDDING_MAX_CONCURRENT)
            logger.info(f"Embedding rate limiter initialized (max concurrent: {EMBEDDING_MAX_CONCURRENT})")

    async def initialize_pool(self) -> None:
        """Initializes the asyncmy connection pool within the running event loop."""
        # Initialize embedding semaphore for rate limiting
        self._init_embedding_semaphore()

        # Initialize multiple pools if configured
        if len(DB_HOSTS) > 1:
            await self.initialize_multiple_pools()
            return

        if not all([DB_USER, DB_PASSWORD]):
            logger.error("Cannot initialize pool due to missing database credentials.")
            raise ConnectionError("Missing database credentials for pool initialization.")

        if self.pool is not None:
            logger.info("Connection pool already initialized.")
            return

        try:
            pool_params = {
                "host": DB_HOST,
                "port": DB_PORT,
                "user": DB_USER,
                "password": DB_PASSWORD,
                "db": DB_NAME,
                "minsize": 1,
                "maxsize": MCP_MAX_POOL_SIZE,
                "autocommit": self.autocommit,
                "pool_recycle": 3600,
                "connect_timeout": DB_CONNECT_TIMEOUT,
            }

            if DB_CHARSET:
                pool_params["charset"] = DB_CHARSET
                logger.info(
                    f"Creating connection pool for {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME} (max size: {MCP_MAX_POOL_SIZE}, charset: {DB_CHARSET})"
                )
            else:
                logger.info(
                    f"Creating connection pool for {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME} (max size: {MCP_MAX_POOL_SIZE})"
                )

            self.pool = await asyncmy.create_pool(**pool_params)

            # Pool warmup - verify connection works
            await self._warmup_pool()
            logger.info("Connection pool initialized and validated successfully.")
        except AsyncMyError as e:
            logger.error(f"Failed to initialize database connection pool: {e}", exc_info=True)
            self.pool = None
            raise
        except Exception as e:
            logger.error(f"An unexpected error occurred during pool initialization: {e}", exc_info=True)
            self.pool = None
            raise

    async def _warmup_pool(self) -> None:
        """Validates the connection pool by executing a simple query."""
        if self.pool is None:
            return
        try:
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute("SELECT 1")
                    await cursor.fetchone()
            logger.debug("Pool warmup successful - connection validated.")
        except Exception as e:
            logger.warning(f"Pool warmup query failed: {e}")

    async def initialize_multiple_pools(self) -> None:
        """Initialize multiple database connection pools."""
        # Initialize embedding semaphore for rate limiting
        self._init_embedding_semaphore()

        logger.info(f"Initializing {len(DB_HOSTS)} database connection pools...")

        for i, host in enumerate(DB_HOSTS):
            port = DB_PORTS[i] if i < len(DB_PORTS) else 3306
            user = DB_USERS[i] if i < len(DB_USERS) else None
            password = DB_PASSWORDS[i] if i < len(DB_PASSWORDS) else None
            db_name = DB_NAMES[i] if i < len(DB_NAMES) else None
            charset = DB_CHARSETS[i] if i < len(DB_CHARSETS) and DB_CHARSETS[i] else None

            if not all([user, password]):
                logger.warning(f"Skipping pool {i}: missing credentials for {host}")
                continue

            conn_name = f"{host}:{port}"
            try:
                pool_params = {
                    "host": host,
                    "port": port,
                    "user": user,
                    "password": password,
                    "db": db_name,
                    "minsize": 1,
                    "maxsize": MCP_MAX_POOL_SIZE,
                    "autocommit": self.autocommit,
                    "pool_recycle": 3600,
                    "connect_timeout": DB_CONNECT_TIMEOUT,
                }
                if charset:
                    pool_params["charset"] = charset

                self.pools[conn_name] = await asyncmy.create_pool(**pool_params)
                logger.info(f"Pool '{conn_name}' initialized for {user}@{host}:{port}/{db_name}")

                # Set first successful pool as default
                if self.pool is None:
                    self.pool = self.pools[conn_name]
                    await self._warmup_pool()
                    logger.info(f"Default pool set to '{conn_name}'")
            except Exception as e:
                logger.error(f"Failed to initialize pool for {conn_name}: {e}", exc_info=True)

    async def close_pool(self) -> None:
        """Closes the connection pool gracefully."""
        # Close multiple pools
        if self.pools:
            logger.info(f"Closing {len(self.pools)} database connection pools...")
            for conn_name, pool in self.pools.items():
                try:
                    pool.close()
                    await pool.wait_closed()
                    logger.info(f"Pool '{conn_name}' closed.")
                except Exception as e:
                    logger.error(f"Error closing pool '{conn_name}': {e}", exc_info=True)
            self.pools.clear()
            self.pool = None  # Prevent double-close; default pool was already closed above

        if self.pool:
            logger.info("Closing database connection pool...")
            try:
                self.pool.close()
                await self.pool.wait_closed()
                logger.info("Database connection pool closed.")
            except Exception as e:
                logger.error(f"Error closing connection pool: {e}", exc_info=True)
            finally:
                self.pool = None

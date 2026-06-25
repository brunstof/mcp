# query.py
"""Read-only query gateway and schema-existence helpers.

`QueryMixin` is the single choke point for all SQL execution: it enforces
read-only mode (with SQL-comment-stripping bypass protection), forwards
parameters unchanged, applies the result-row cap, and records metrics. The
existence helpers (`_database_exists`, `_table_exists`, `_is_vector_store`)
build on it.

This is the module the Phase-3 driver migration (asyncmy -> mariadb-connector,
``%s`` -> ``?``) will touch; ``src/tests/test_execute_query_unit.py`` is its
safety net. ``MCP_MAX_RESULTS`` is read as ``config.MCP_MAX_RESULTS`` at call
time so the limit stays patchable in tests.
"""

import re
import time
from typing import Any

from asyncmy.cursors import DictCursor
from asyncmy.errors import Error as AsyncMyError

import config
from base import ServerBase
from config import DB_NAME, logger


class QueryMixin(ServerBase):
    """SQL execution gateway plus database/table existence checks."""

    async def _execute_query(
        self, sql: str, params: tuple | None = None, database: str | None = None, limit_results: bool = True
    ) -> list[dict[str, Any]]:
        """Helper function to execute SELECT queries using the pool.

        Args:
            sql: The SQL query to execute
            params: Optional tuple of parameters for parameterized queries
            database: Optional database to switch to before executing
            limit_results: If True, limits results to MCP_MAX_RESULTS (default True)

        Returns:
            List of result dictionaries

        Raises:
            RuntimeError: If pool not available or database error
            PermissionError: If query blocked by read-only mode
        """
        if self.pool is None:
            logger.error("Connection pool is not initialized.")
            raise RuntimeError("Database connection pool not available.")

        allowed_prefixes = ("SELECT", "SHOW", "DESC", "DESCRIBE", "USE")

        # Strip SQL comments from query
        # Remove single-line comments (-- comment)
        sql_no_comments = re.sub(r"--.*?$", "", sql, flags=re.MULTILINE)
        # Remove multi-line comments (/* comment */)
        sql_no_comments = re.sub(r"/\*.*?\*/", "", sql_no_comments, flags=re.DOTALL)
        sql_no_comments = sql_no_comments.strip()

        query_upper = sql_no_comments.upper()
        is_allowed_read_query = any(query_upper.startswith(prefix) for prefix in allowed_prefixes)

        if self.is_read_only and not is_allowed_read_query:
            logger.warning(f"Blocked potentially non-read-only query in read-only mode: {sql[:100]}...")
            raise PermissionError("Operation forbidden: Server is in read-only mode.")

        logger.info(f"Executing query (DB: {database or DB_NAME}): {sql[:100]}...")
        if params:
            logger.debug(f"Parameters: {params}")

        conn = None
        start_time = time.time()
        try:
            self._metrics["pool_acquisitions"] += 1
            async with self.pool.acquire() as conn:
                async with conn.cursor(cursor=DictCursor) as cursor:
                    # Only switch database context if explicitly requested
                    # This avoids unnecessary SELECT DATABASE() calls
                    if database:
                        await cursor.execute(f"USE `{database}`")

                    await cursor.execute(sql, params or ())
                    results = await cursor.fetchall()

                    # Apply result limit for safety (prevent memory issues with large results)
                    if limit_results and results and len(results) > config.MCP_MAX_RESULTS:
                        logger.warning(f"Query returned {len(results)} rows, limiting to {config.MCP_MAX_RESULTS}")
                        results = results[: config.MCP_MAX_RESULTS]

                    elapsed_ms = (time.time() - start_time) * 1000
                    self._metrics["queries_executed"] += 1
                    self._metrics["total_query_time_ms"] += int(elapsed_ms)
                    logger.info(f"Query executed successfully, {len(results)} rows returned in {elapsed_ms:.1f}ms.")
                    return results if results else []
        except AsyncMyError as e:
            self._metrics["query_errors"] += 1
            conn_state = f"Connection: {'acquired' if conn else 'not acquired'}"
            logger.error(f"Database error executing query ({conn_state}): {e}", exc_info=True)
            raise RuntimeError(f"Database error: {e}") from e
        except PermissionError as e:
            logger.warning(f"Permission denied: {e}")
            raise e
        except Exception as e:
            self._metrics["query_errors"] += 1
            if isinstance(e, RuntimeError) and "Event loop is closed" in str(e):
                logger.critical("Detected closed event loop during query execution!", exc_info=True)
                raise RuntimeError("Event loop closed unexpectedly during query.") from e
            conn_state = f"Connection: {'acquired' if conn else 'not acquired'}"
            logger.error(f"Unexpected error during query execution ({conn_state}): {e}", exc_info=True)
            raise RuntimeError(f"An unexpected error occurred: {e}") from e

    async def _database_exists(self, database_name: str) -> bool:
        """Checks if a database exists."""
        if not database_name or not database_name.isidentifier():
            logger.warning(f"_database_exists called with invalid database_name: {database_name}")
            return False

        sql = "SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = %s"
        try:
            results = await self._execute_query(sql, params=(database_name,), database="information_schema")
            return len(results) > 0
        except Exception as e:
            logger.error(f"Error checking if database '{database_name}' exists: {e}", exc_info=True)
            return False

    async def _table_exists(self, database_name: str, table_name: str) -> bool:
        """Checks if a table exists in the given database."""
        if not database_name or not database_name.isidentifier() or not table_name or not table_name.isidentifier():
            logger.warning(f"_table_exists called with invalid names: db='{database_name}', table='{table_name}'")
            return False

        sql = "SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s"
        try:
            results = await self._execute_query(sql, params=(database_name, table_name), database="information_schema")
            return len(results) > 0
        except Exception as e:
            logger.error(f"Error checking if table '{database_name}.{table_name}' exists: {e}", exc_info=True)
            return False

    async def _is_vector_store(self, database_name: str, table_name: str) -> bool:
        """
        Checks if the specified table in the given database is a vector store.
        A table is considered a vector store if it has an indexed column named 'embedding'
        with a data type of 'VECTOR'.

        Parameters:
        - database_name (str): The name of the database.
        - table_name (str): The name of the table to check.

        Returns:
        - bool: True if the table is a vector store, False otherwise.
        """
        logger.debug(f"Checking if '{database_name}.{table_name}' is a vector store.")

        if not database_name or not database_name.isidentifier() or not table_name or not table_name.isidentifier():
            logger.warning(f"_is_vector_store called with invalid names: db='{database_name}', table='{table_name}'")
            return False

        # SQL query to verify vector store criteria
        sql_query = """
        SELECT COUNT(T1.TABLE_NAME) AS vector_store_count
        FROM information_schema.COLUMNS AS T1
        INNER JOIN information_schema.STATISTICS AS T2
            ON T1.TABLE_SCHEMA = T2.TABLE_SCHEMA
            AND T1.TABLE_NAME = T2.TABLE_NAME
            AND T1.COLUMN_NAME = T2.COLUMN_NAME
        WHERE T1.TABLE_SCHEMA = %s
          AND T1.TABLE_NAME = %s
          AND T1.COLUMN_NAME = 'embedding'
          AND UPPER(T1.DATA_TYPE) = 'VECTOR';
        """
        try:
            results = await self._execute_query(
                sql_query, params=(database_name, table_name), database="information_schema"
            )
            if results and results[0].get("vector_store_count", 0) > 0:
                logger.debug(f"Confirmation: '{database_name}.{table_name}' is a vector store.")
                return True
            else:
                logger.debug(f"Confirmation: '{database_name}.{table_name}' is NOT a vector store.")
                return False
        except Exception as e:
            logger.error(f"Error checking if '{database_name}.{table_name}' is a vector store: {e}", exc_info=True)
            return False  # Treat errors as "not a vector store" for safety in deletion context

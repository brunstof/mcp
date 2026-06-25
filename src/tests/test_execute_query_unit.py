"""Unit tests for MariaDBServer._execute_query (no live database required).

The connection pool is mocked, so these tests isolate the query-gateway logic:
read-only enforcement, SQL-comment-stripping bypass protection, parameter
forwarding and result limiting.

They are deliberately driver-agnostic about *values* but assert that whatever
SQL/params the caller passes are forwarded to ``cursor.execute`` unchanged.
This is the safety net for the planned asyncmy -> mariadb-connector migration
(which switches the parameter placeholder from ``%s`` to ``?``): if that change
ever stops forwarding params correctly, these tests fail.
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from server import MariaDBServer


class _AsyncCM:
    """Minimal async context manager wrapping a fixed value."""

    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, *exc):
        return False


def _make_pool(rows=None):
    """Build a mock pool whose cursor returns ``rows`` from fetchall()."""
    cursor = MagicMock(name="cursor")
    cursor.execute = AsyncMock()
    cursor.fetchall = AsyncMock(return_value=rows if rows is not None else [])

    conn = MagicMock(name="conn")
    conn.cursor = MagicMock(return_value=_AsyncCM(cursor))

    pool = MagicMock(name="pool")
    pool.acquire = MagicMock(return_value=_AsyncCM(conn))
    return pool, cursor


class TestExecuteQueryUnit(unittest.IsolatedAsyncioTestCase):
    def _server(self, *, read_only, pool=None):
        server = MariaDBServer()
        server.is_read_only = read_only
        server.pool = pool
        return server

    # --- pool availability -------------------------------------------------

    async def test_pool_none_raises_runtimeerror(self):
        server = self._server(read_only=True, pool=None)
        with self.assertRaises(RuntimeError):
            await server._execute_query("SELECT 1")

    # --- allowed read queries ---------------------------------------------

    async def test_select_returns_rows(self):
        pool, cursor = _make_pool(rows=[{"x": 1}])
        server = self._server(read_only=True, pool=pool)

        result = await server._execute_query("SELECT 1")

        self.assertEqual(result, [{"x": 1}])
        cursor.execute.assert_awaited_once_with("SELECT 1", ())

    async def test_allowed_prefixes_pass_in_readonly(self):
        for sql in ("SHOW DATABASES", "DESCRIBE t", "DESC t", "USE `d`", "select 1"):
            pool, cursor = _make_pool(rows=[])
            server = self._server(read_only=True, pool=pool)
            await server._execute_query(sql)
            cursor.execute.assert_awaited()  # reached execution, not blocked

    # --- parameter forwarding (paramstyle safety net) ---------------------

    async def test_params_forwarded_unchanged(self):
        pool, cursor = _make_pool(rows=[])
        server = self._server(read_only=True, pool=pool)

        sql = "SELECT * FROM information_schema.TABLES WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s"
        params = ("information_schema", "TABLES")
        await server._execute_query(sql, params=params, database="information_schema")

        # USE happens first, then the real query with the exact params tuple.
        cursor.execute.assert_any_await(sql, params)

    # --- read-only enforcement --------------------------------------------

    async def test_readonly_blocks_write(self):
        for sql in ("DELETE FROM t", "INSERT INTO t VALUES (1)", "UPDATE t SET a=1", "DROP TABLE t"):
            pool, cursor = _make_pool()
            server = self._server(read_only=True, pool=pool)
            with self.assertRaises(PermissionError):
                await server._execute_query(sql)
            cursor.execute.assert_not_awaited()

    async def test_readonly_blocks_line_comment_bypass(self):
        # A leading line comment must not smuggle a write past the prefix check.
        pool, cursor = _make_pool()
        server = self._server(read_only=True, pool=pool)
        with self.assertRaises(PermissionError):
            await server._execute_query("-- harmless\nDELETE FROM t")
        cursor.execute.assert_not_awaited()

    async def test_readonly_blocks_block_comment_bypass(self):
        pool, cursor = _make_pool()
        server = self._server(read_only=True, pool=pool)
        with self.assertRaises(PermissionError):
            await server._execute_query("/* comment */ DROP TABLE t")
        cursor.execute.assert_not_awaited()

    async def test_write_allowed_when_not_readonly(self):
        pool, cursor = _make_pool(rows=[])
        server = self._server(read_only=False, pool=pool)
        await server._execute_query("DELETE FROM t")
        cursor.execute.assert_awaited_once_with("DELETE FROM t", ())

    # --- database context switch ------------------------------------------

    async def test_database_switch_issues_use_first(self):
        pool, cursor = _make_pool(rows=[])
        server = self._server(read_only=True, pool=pool)
        await server._execute_query("SELECT 1", database="mydb")

        first_call = cursor.execute.await_args_list[0]
        self.assertEqual(first_call.args[0], "USE `mydb`")

    # --- result limiting --------------------------------------------------

    async def test_results_limited_to_max(self):
        rows = [{"n": i} for i in range(5)]
        pool, cursor = _make_pool(rows=rows)
        server = self._server(read_only=True, pool=pool)

        with patch("server.MCP_MAX_RESULTS", 2):
            result = await server._execute_query("SELECT n FROM t")

        self.assertEqual(len(result), 2)

    async def test_results_not_limited_when_disabled(self):
        rows = [{"n": i} for i in range(5)]
        pool, cursor = _make_pool(rows=rows)
        server = self._server(read_only=True, pool=pool)

        with patch("server.MCP_MAX_RESULTS", 2):
            result = await server._execute_query("SELECT n FROM t", limit_results=False)

        self.assertEqual(len(result), 5)


if __name__ == "__main__":
    unittest.main()

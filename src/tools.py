# tools.py
"""Standard (non-vector) MCP tool implementations.

`StandardToolsMixin` provides the database/table introspection and SQL-execution
tools. It builds on `QueryMixin` (inherited) for the actual query gateway and
existence checks.
"""

from typing import Any

from config import logger
from query import QueryMixin


class StandardToolsMixin(QueryMixin):
    """Standard SQL tools: list/describe databases and tables, execute SQL, create database."""

    async def list_databases(self) -> list[str]:
        """Lists all accessible databases on the connected MariaDB server."""
        logger.info("TOOL START: list_databases called.")
        sql = "SHOW DATABASES"
        try:
            results = await self._execute_query(sql)
            db_list = [row["Database"] for row in results if "Database" in row]
            logger.info(f"TOOL END: list_databases completed. Databases found: {len(db_list)}.")
            return db_list
        except Exception as e:
            logger.error(f"TOOL ERROR: list_databases failed: {e}", exc_info=True)
            raise

    async def list_tables(self, database_name: str) -> list[str]:
        """Lists all tables within the specified database."""
        logger.info(f"TOOL START: list_tables called. database_name={database_name}")
        if not database_name or not database_name.isidentifier():
            logger.warning(f"TOOL WARNING: list_tables called with invalid database_name: {database_name}")
            raise ValueError(f"Invalid database name provided: {database_name}")
        sql = "SHOW TABLES"
        try:
            results = await self._execute_query(sql, database=database_name)
            table_list = [list(row.values())[0] for row in results if row]
            logger.info(f"TOOL END: list_tables completed. Tables found: {len(table_list)}.")
            return table_list
        except Exception as e:
            logger.error(f"TOOL ERROR: list_tables failed for database_name={database_name}: {e}", exc_info=True)
            raise

    async def get_table_schema(self, database_name: str, table_name: str) -> dict[str, Any]:
        """
        Retrieves the schema (column names, types, nullability, keys, default values)
        for a specific table in a database.
        """
        logger.info(f"TOOL START: get_table_schema called. database_name={database_name}, table_name={table_name}")
        if not database_name or not database_name.isidentifier():
            logger.warning(f"TOOL WARNING: get_table_schema called with invalid database_name: {database_name}")
            raise ValueError(f"Invalid database name provided: {database_name}")
        if not table_name or not table_name.isidentifier():
            logger.warning(f"TOOL WARNING: get_table_schema called with invalid table_name: {table_name}")
            raise ValueError(f"Invalid table name provided: {table_name}")

        sql = f"DESCRIBE `{database_name}`.`{table_name}`"
        try:
            schema_results = await self._execute_query(sql)
            schema_info = {}
            if not schema_results:
                exists_sql = "SELECT COUNT(*) as count FROM information_schema.tables WHERE table_schema = %s AND table_name = %s"
                exists_result = await self._execute_query(exists_sql, params=(database_name, table_name))
                if not exists_result or exists_result[0]["count"] == 0:
                    logger.warning(f"TOOL WARNING: Table '{database_name}'.'{table_name}' not found or inaccessible.")
                    raise FileNotFoundError(f"Table '{database_name}'.'{table_name}' not found or inaccessible.")
                else:
                    logger.warning(
                        f"Could not describe table '{database_name}'.'{table_name}'. It might be a view or lack permissions."
                    )

            for row in schema_results:
                col_name = row.get("Field")
                if col_name:
                    schema_info[col_name] = {
                        "type": row.get("Type"),
                        "nullable": row.get("Null", "").upper() == "YES",
                        "key": row.get("Key"),
                        "default": row.get("Default"),
                        "extra": row.get("Extra"),
                    }
            logger.info(
                f"TOOL END: get_table_schema completed. Columns found: {len(schema_info)}. Keys: {list(schema_info.keys())}"
            )
            return schema_info
        except FileNotFoundError as e:
            logger.warning(f"TOOL WARNING: get_table_schema table not found: {e}")
            raise e
        except Exception as e:
            logger.error(
                f"TOOL ERROR: get_table_schema failed for database_name={database_name}, table_name={table_name}: {e}",
                exc_info=True,
            )
            raise RuntimeError(f"Could not retrieve schema for table '{database_name}.{table_name}'.") from e

    async def get_table_schema_with_relations(self, database_name: str, table_name: str) -> dict[str, Any]:
        """
        Retrieves table schema with foreign key relationship information.
        Includes all basic schema info plus foreign key relationships and referenced tables.
        """
        logger.info(
            f"TOOL START: get_table_schema_with_relations called. database_name={database_name}, table_name={table_name}"
        )
        if not database_name or not database_name.isidentifier():
            logger.warning(
                f"TOOL WARNING: get_table_schema_with_relations called with invalid database_name: {database_name}"
            )
            raise ValueError(f"Invalid database name provided: {database_name}")
        if not table_name or not table_name.isidentifier():
            logger.warning(
                f"TOOL WARNING: get_table_schema_with_relations called with invalid table_name: {table_name}"
            )
            raise ValueError(f"Invalid table name provided: {table_name}")

        try:
            # 1. Get basic schema information
            basic_schema = await self.get_table_schema(database_name, table_name)

            # 2. Retrieve foreign key information
            fk_sql = """
            SELECT
                kcu.COLUMN_NAME as column_name,
                kcu.CONSTRAINT_NAME as constraint_name,
                kcu.REFERENCED_TABLE_NAME as referenced_table,
                kcu.REFERENCED_COLUMN_NAME as referenced_column,
                rc.UPDATE_RULE as on_update,
                rc.DELETE_RULE as on_delete
            FROM information_schema.KEY_COLUMN_USAGE kcu
            INNER JOIN information_schema.REFERENTIAL_CONSTRAINTS rc
                ON kcu.CONSTRAINT_NAME = rc.CONSTRAINT_NAME
                AND kcu.CONSTRAINT_SCHEMA = rc.CONSTRAINT_SCHEMA
            WHERE kcu.TABLE_SCHEMA = %s
              AND kcu.TABLE_NAME = %s
              AND kcu.REFERENCED_TABLE_NAME IS NOT NULL
            ORDER BY kcu.CONSTRAINT_NAME, kcu.ORDINAL_POSITION
            """

            fk_results = await self._execute_query(fk_sql, params=(database_name, table_name))

            # 3. Add foreign key information to the basic schema
            enhanced_schema = {}
            for col_name, col_info in basic_schema.items():
                enhanced_schema[col_name] = col_info.copy()
                enhanced_schema[col_name]["foreign_key"] = None

            # 4. Add foreign key information to the corresponding columns
            for fk_row in fk_results:
                column_name = fk_row["column_name"]
                if column_name in enhanced_schema:
                    enhanced_schema[column_name]["foreign_key"] = {
                        "constraint_name": fk_row["constraint_name"],
                        "referenced_table": fk_row["referenced_table"],
                        "referenced_column": fk_row["referenced_column"],
                        "on_update": fk_row["on_update"],
                        "on_delete": fk_row["on_delete"],
                    }

            # 5. Return the enhanced schema with foreign key relations
            result = {"table_name": table_name, "columns": enhanced_schema}

            logger.info(
                f"TOOL END: get_table_schema_with_relations completed. Columns: {len(enhanced_schema)}, Foreign keys: {len(fk_results)}"
            )
            return result

        except Exception as e:
            logger.error(
                f"TOOL ERROR: get_table_schema_with_relations failed for database_name={database_name}, table_name={table_name}: {e}",
                exc_info=True,
            )
            raise RuntimeError(
                f"Could not retrieve schema with relations for table '{database_name}.{table_name}': {str(e)}"
            ) from e

    async def execute_sql(
        self, sql_query: str, database_name: str, parameters: list[Any] | None = None
    ) -> list[dict[str, Any]]:
        """
        Executes a read-only SQL query (primarily SELECT, SHOW, DESCRIBE) against a specified database
        and returns the results. Uses parameterized queries for safety.
        Example `parameters`: ["value1", 123] corresponding to %s placeholders in `sql_query`.
        """
        logger.info(
            f"TOOL START: execute_sql called. database_name={database_name}, sql_query={sql_query[:100]}, parameters={parameters}"
        )
        if database_name and not database_name.isidentifier():
            logger.warning(f"TOOL WARNING: execute_sql called with invalid database_name: {database_name}")
            raise ValueError(f"Invalid database name provided: {database_name}")
        param_tuple = tuple(parameters) if parameters is not None else None
        try:
            results = await self._execute_query(sql_query, params=param_tuple, database=database_name)
            logger.info(f"TOOL END: execute_sql completed. Rows returned: {len(results)}.")
            return results
        except Exception as e:
            logger.error(
                f"TOOL ERROR: execute_sql failed for database_name={database_name}, sql_query={sql_query[:100]}, parameters={parameters}: {e}",
                exc_info=True,
            )
            raise

    async def create_database(self, database_name: str) -> dict[str, Any]:
        """
        Creates a new database if it doesn't exist.
        """
        logger.info(f"TOOL START: create_database called for database: '{database_name}'")
        if not database_name or not database_name.isidentifier():
            logger.error(f"Invalid database_name for creation: '{database_name}'. Must be a valid identifier.")
            raise ValueError(f"Invalid database_name for creation: '{database_name}'. Must be a valid identifier.")

        # Check existence first to provide a clear message, though CREATE DATABASE IF NOT EXISTS is idempotent
        if await self._database_exists(database_name):
            message = f"Database '{database_name}' already exists."
            logger.info(f"TOOL END: create_database. {message}")
            return {"status": "exists", "message": message, "database_name": database_name}

        sql = f"CREATE DATABASE IF NOT EXISTS `{database_name}`;"

        try:
            await self._execute_query(sql, database=None)

            message = f"Database '{database_name}' created successfully."
            logger.info(f"TOOL END: create_database. {message}")
            return {"status": "success", "message": message, "database_name": database_name}
        except Exception as e:
            error_message = f"Failed to create database '{database_name}'."
            logger.error(f"TOOL ERROR: create_database. {error_message} Error: {e}", exc_info=True)
            raise RuntimeError(f"{error_message} Reason: {str(e)}") from e

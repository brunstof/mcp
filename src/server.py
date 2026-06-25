# server.py
"""MariaDB MCP Server entry point and composition.

`MariaDBServer` composes the pool / query / standard-tool / vector-tool mixins
into a single FastMCP server. This module owns only the cross-cutting concerns:
tool registration, the ``/health`` endpoint and metrics, the async run loop, and
the CLI entry point. All database behavior lives in the mixins:

- `base.ServerBase`        — shared state and construction
- `db_pool.PoolMixin`      — connection-pool lifecycle
- `query.QueryMixin`       — read-only query gateway + existence helpers
- `tools.StandardToolsMixin`   — standard SQL tools
- `vector_store.VectorToolsMixin` — vector-store tools
"""

import argparse
import time
from functools import partial
from typing import Any

import anyio
from asyncmy.errors import Error as AsyncMyError
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse

from config import (
    ALLOWED_HOSTS,
    ALLOWED_ORIGINS,
    EMBEDDING_PROVIDER,
    logger,
)
from db_pool import PoolMixin
from vector_store import VectorToolsMixin


# --- MariaDB MCP Server Class ---
class MariaDBServer(PoolMixin, VectorToolsMixin):
    """
    MCP Server exposing tools to interact with a MariaDB database.

    Composes the pool, query, and tool mixins. Construction and shared state live
    in `base.ServerBase`; the database behavior lives in the inherited mixins.

    MRO: MariaDBServer -> PoolMixin -> VectorToolsMixin -> StandardToolsMixin
         -> QueryMixin -> ServerBase -> object
    """

    # --- Tool Registration (Synchronous) ---
    def register_tools(self) -> None:
        """Registers the class methods as MCP tools using the instance. This is synchronous."""
        if self.pool is None:
            logger.error("Cannot register tools: Database pool is not initialized.")
            raise RuntimeError("Database pool must be initialized before registering tools.")

        @self.mcp.tool
        async def list_databases() -> list[str]:
            """Lists all accessible databases on the connected MariaDB server."""
            return await self.list_databases()

        @self.mcp.tool
        async def list_tables(database_name: str) -> list[str]:
            """Lists all tables within the specified database."""
            return await self.list_tables(database_name)

        @self.mcp.tool
        async def get_table_schema(database_name: str, table_name: str) -> dict[str, Any]:
            """Retrieves the schema for a specific table in a database."""
            return await self.get_table_schema(database_name, table_name)

        @self.mcp.tool
        async def get_table_schema_with_relations(database_name: str, table_name: str) -> dict[str, Any]:
            """Retrieves table schema with foreign key relationship information."""
            return await self.get_table_schema_with_relations(database_name, table_name)

        @self.mcp.tool
        async def execute_sql(
            sql_query: str, database_name: str, parameters: list[Any] | None = None
        ) -> list[dict[str, Any]]:
            """Executes a read-only SQL query against a specified database."""
            return await self.execute_sql(sql_query, database_name, parameters)

        @self.mcp.tool
        async def create_database(database_name: str) -> dict[str, Any]:
            """Creates a new database if it doesn't exist."""
            return await self.create_database(database_name)

        if EMBEDDING_PROVIDER is not None:

            @self.mcp.tool
            async def create_vector_store(
                database_name: str,
                vector_store_name: str,
                model_name: str | None = None,
                distance_function: str | None = None,
            ) -> dict:
                """Creates a table which stores embeddings."""
                return await self.create_vector_store(database_name, vector_store_name, model_name, distance_function)

            @self.mcp.tool
            async def list_vector_stores(database_name: str) -> list[str]:
                """Lists all vector stores in a database."""
                return await self.list_vector_stores(database_name)

            @self.mcp.tool
            async def delete_vector_store(database_name: str, vector_store_name: str) -> dict[str, Any]:
                """Deletes a vector store from the specified database."""
                return await self.delete_vector_store(database_name, vector_store_name)

            @self.mcp.tool
            async def insert_docs_vector_store(
                database_name: str, vector_store_name: str, documents: list[str], metadata: list[dict] | None = None
            ) -> dict:
                """Insert a batch of documents into a vector store."""
                return await self.insert_docs_vector_store(database_name, vector_store_name, documents, metadata)

            @self.mcp.tool
            async def search_vector_store(
                user_query: str, database_name: str, vector_store_name: str, k: int = 7
            ) -> list:
                """Search a vector store for similar documents."""
                return await self.search_vector_store(user_query, database_name, vector_store_name, k)

        logger.info("Registered MCP tools explicitly.")

        # Register /health endpoint for HTTP/SSE transports
        self.mcp.custom_route("/health", methods=["GET"])(self._health_endpoint)
        logger.info("Registered /health endpoint.")

    def get_health(self) -> dict[str, Any]:
        """Returns health check information for the server."""
        uptime_seconds = time.time() - self._start_time
        pool_status = "connected" if self.pool is not None else "disconnected"

        # Calculate average query time
        avg_query_time: float = 0
        if self._metrics["queries_executed"] > 0:
            avg_query_time = self._metrics["total_query_time_ms"] / self._metrics["queries_executed"]

        return {
            "status": "healthy" if self.pool is not None else "unhealthy",
            "uptime_seconds": round(uptime_seconds, 2),
            "pool_status": pool_status,
            "read_only_mode": self.is_read_only,
            "embedding_provider": EMBEDDING_PROVIDER,
            "metrics": {
                "queries_executed": self._metrics["queries_executed"],
                "query_errors": self._metrics["query_errors"],
                "avg_query_time_ms": round(avg_query_time, 2),
                "embeddings_generated": self._metrics["embeddings_generated"],
                "pool_acquisitions": self._metrics["pool_acquisitions"],
            },
        }

    async def _health_endpoint(self, request):
        """Starlette endpoint handler for /health."""
        health_data = self.get_health()
        status_code = 200 if health_data["status"] == "healthy" else 503
        return JSONResponse(health_data, status_code=status_code)

    # --- Async Main Server Logic ---
    async def run_async_server(self, transport="stdio", host="127.0.0.1", port=9001, path="/mcp") -> None:
        """
        Initializes pool, registers tools, and runs the appropriate async MCP listener.
        This method should be the target for anyio.run().
        """
        try:
            # 1. Initialize pool within the anyio-managed loop
            await self.initialize_pool()

            # 2. Register tools (synchronous part, but called from async context)
            self.register_tools()

            # 3. Prepare transport arguments
            transport_kwargs = {}
            if transport != "stdio":
                # Broaden CORS and include OPTIONS and credentials to accommodate
                # browser-based clients and websocket upgrade flows used by some
                # agent UIs. Keep TrustedHostMiddleware to limit allowed hosts.
                middleware = [
                    Middleware(
                        CORSMiddleware,
                        allow_origins=ALLOWED_ORIGINS,
                        allow_methods=["GET", "POST", "OPTIONS"],
                        allow_headers=["*"],
                        allow_credentials=True,
                        expose_headers=["*"],
                    ),
                    Middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS),
                ]

            if transport == "sse":
                transport_kwargs = {"host": host, "port": port, "middleware": middleware}
                logger.info(f"Starting MCP server via {transport} on {host}:{port}...")
            elif transport == "http":
                transport_kwargs = {"host": host, "port": port, "path": path, "middleware": middleware}
                logger.info(f"Starting MCP server via {transport} on {host}:{port}{path}...")
            elif transport == "stdio":
                logger.info(f"Starting MCP server via {transport}...")
            else:
                logger.error(f"Unsupported transport type: {transport}")
                return

            # 4. Run the appropriate async listener from FastMCP
            await self.mcp.run_async(transport=transport, **transport_kwargs)

        except (ConnectionError, AsyncMyError, RuntimeError) as e:
            logger.critical(f"Server setup failed: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.critical(f"Server execution failed with an unexpected error: {e}", exc_info=True)
            raise
        finally:
            await self.close_pool()


# --- Main Execution Block ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MariaDB MCP Server")
    parser.add_argument(
        "--transport",
        type=str,
        default="stdio",
        choices=["stdio", "sse", "http"],
        help="MCP transport protocol (stdio, sse, or http)",
    )
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host for SSE or HTTP transport")
    parser.add_argument("--port", type=int, default=9001, help="Port for SSE or HTTP transport")
    parser.add_argument("--path", type=str, default="/mcp", help="Path for HTTP transport (default: /mcp)")
    args = parser.parse_args()

    # 1. Create the server instance
    server = MariaDBServer()
    exit_code = 0

    try:
        # 2. Use anyio.run to manage the event loop and call the main async server logic
        anyio.run(
            partial(server.run_async_server, transport=args.transport, host=args.host, port=args.port, path=args.path)
        )
        logger.info("Server finished gracefully.")

    except KeyboardInterrupt:
        logger.info("Server execution interrupted by user.")
    except Exception as e:
        logger.critical(f"Server failed to start or crashed: {e}", exc_info=True)
        exit_code = 1
    finally:
        logger.info(f"Server exiting with code {exit_code}.")

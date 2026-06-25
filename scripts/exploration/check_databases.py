import json
import os
import sys

# Make the project's src/ importable regardless of CWD
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import anyio  # noqa: E402
from fastmcp.client import Client  # noqa: E402

from server import MariaDBServer  # noqa: E402


async def main():
    server = MariaDBServer()

    async with anyio.create_task_group() as tg:
        async def run_server():
            await server.run_async_server('stdio')

        tg.start_soon(run_server)
        await anyio.sleep(2)  # Wait for server to start

        async with Client(server.mcp) as client:
            # List databases
            result = await client.call_tool('list_databases', {})
            databases = json.loads(result.text)
            print("=== Databases ===")
            for db in sorted(databases):
                print(f"  - {db}")

            print("\n=== Tables per Database ===")
            # List tables for each database (limit to first 10 for brevity)
            for db in sorted(databases)[:10]:
                try:
                    result = await client.call_tool('list_tables', {'database_name': db})
                    tables = json.loads(result.text)
                    print(f"\n{db}:")
                    if tables:
                        for t in tables[:20]:  # Limit to first 20 tables
                            print(f"  - {t}")
                        if len(tables) > 20:
                            print(f"  ... and {len(tables) - 20} more")
                    else:
                        print("  (empty)")
                except Exception as e:
                    print(f"\n{db}: (error - {e})")

        tg.cancel_scope.cancel()


anyio.run(main)

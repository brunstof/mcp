import os
import sys

# Make the project's src/ importable regardless of CWD
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import anyio  # noqa: E402

from server import MariaDBServer  # noqa: E402


async def main():
    server = MariaDBServer()
    await server.initialize_pool()
    pool = server.pool

    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            # Get databases
            await cur.execute("SHOW DATABASES")
            dbs = await cur.fetchall()
            databases = sorted([r[0] for r in dbs])

            print("=== Databases ===")
            for db in databases:
                print(f"  - {db}")

            print("\n=== Tables per Database ===")
            for db in databases[:15]:
                try:
                    await cur.execute(f"SHOW TABLES FROM `{db}`")
                    tables = await cur.fetchall()
                    table_names = [t[0] for t in tables]
                    print(f"\n{db}:")
                    if table_names:
                        for t in table_names[:25]:
                            print(f"  - {t}")
                        if len(table_names) > 25:
                            print(f"  ... and {len(table_names) - 25} more")
                    else:
                        print("  (empty)")
                except Exception as e:
                    print(f"\n{db}: (error - {e})")


anyio.run(main)

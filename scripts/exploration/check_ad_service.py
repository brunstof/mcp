import asyncio

import asyncmy

from _conn import conn_kwargs


async def query():
    conn = await asyncmy.connect(**conn_kwargs())
    async with conn.cursor() as cur:
        await cur.execute("SHOW DATABASES LIKE '%ad%'")
        dbs = await cur.fetchall()
        print("Databases with 'ad':")
        for db in dbs:
            print(f"  {db[0]}")

        await cur.execute("SHOW DATABASES LIKE '%service%'")
        dbs = await cur.fetchall()
        print("\nDatabases with 'service':")
        for db in dbs:
            print(f"  {db[0]}")

        # Check kbme databases for cost center
        for db_name in ['kbme_db', 'kbme_db_tables']:
            try:
                await cur.execute(f'USE `{db_name}`')
                await cur.execute('SHOW TABLES')
                tables = await cur.fetchall()
                print(f"\n{db_name} tables:")
                for tbl in tables:
                    print(f"  {tbl[0]}")
            except Exception:
                pass

    conn.close()


asyncio.run(query())

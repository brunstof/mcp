import asyncio

import asyncmy

from _conn import conn_kwargs


async def query():
    conn = await asyncmy.connect(**conn_kwargs())
    async with conn.cursor() as cur:
        await cur.execute('SHOW DATABASES')
        dbs = await cur.fetchall()
        print("Databases:")
        for db in dbs:
            print(f"  {db[0]}")

        # Check matgrade
        await cur.execute(
            "SELECT SCHEMA_NAME FROM information_schema.SCHEMATA "
            "WHERE SCHEMA_NAME IN ('matgrade', 'ad_service')"
        )
        found = await cur.fetchall()

        for db in found:
            db_name = db[0]
            print(f"\n=== {db_name} ===\n")
            await cur.execute(f'USE `{db_name}`')
            await cur.execute('SHOW TABLES')
            tables = await cur.fetchall()

            for table in tables:
                tbl = table[0]
                print(f"Table: {tbl}")
                await cur.execute(
                    "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND COLUMN_NAME LIKE '%Manager%Email%'",
                    (db_name, tbl),
                )
                mgr = await cur.fetchall()
                if mgr:
                    for col in mgr:
                        await cur.execute(f'SELECT COUNT(DISTINCT `{col[0]}`) FROM `{tbl}`')
                        cnt = await cur.fetchone()
                        print(f"  >>> {col[0]}: {cnt[0]} distinct values")
                print()

    conn.close()


asyncio.run(query())

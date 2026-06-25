import asyncio

import asyncmy

from _conn import conn_kwargs


async def query():
    conn = await asyncmy.connect(**conn_kwargs())
    async with conn.cursor() as cur:
        # Search for ManagerEmail across all databases
        await cur.execute("""
            SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME
            FROM information_schema.COLUMNS
            WHERE COLUMN_NAME LIKE '%Manager%Email%'
            AND TABLE_SCHEMA NOT IN ('information_schema', 'mysql', 'performance_schema', 'sys')
        """)
        results = await cur.fetchall()

        if results:
            print("Found ManagerEmail columns:\n")
            for row in results:
                db, tbl, col = row
                print(f"Database: {db}, Table: {tbl}, Column: {col}")
                await cur.execute(f'USE `{db}`')
                await cur.execute(f'SELECT COUNT(DISTINCT `{col}`) FROM `{tbl}`')
                cnt = await cur.fetchone()
                print(f"  >>> Distinct values: {cnt[0]}\n")
        else:
            print("No ManagerEmail columns found. Searching for 'cost' tables...")
            await cur.execute("""
                SELECT TABLE_SCHEMA, TABLE_NAME
                FROM information_schema.TABLES
                WHERE TABLE_NAME LIKE '%cost%'
                AND TABLE_SCHEMA NOT IN ('information_schema', 'mysql', 'performance_schema', 'sys')
            """)
            cost_tables = await cur.fetchall()
            for row in cost_tables:
                print(f"{row[0]}.{row[1]}")

    conn.close()


asyncio.run(query())

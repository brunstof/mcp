import asyncio

import asyncmy

from _conn import conn_kwargs


async def query():
    conn = await asyncmy.connect(**conn_kwargs(db='ad_service'))
    async with conn.cursor() as cur:
        await cur.execute('SHOW DATABASES')
        dbs = await cur.fetchall()
        print("Databases:")
        for db in dbs:
            print(f"  {db[0]}")

        await cur.execute(
            "SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = %s",
            ('ad_service',),
        )
        if await cur.fetchone():
            print("\n=== ad_service database found ===")
            await cur.execute('USE ad_service')
            await cur.execute('SHOW TABLES')
            tables = await cur.fetchall()

            for table in tables:
                print(f"\nTable: {table[0]}")
                await cur.execute(
                    "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA='ad_service' AND TABLE_NAME=%s AND COLUMN_NAME LIKE '%Manager%'",
                    (table[0],),
                )
                mgr_cols = await cur.fetchall()

                if mgr_cols:
                    for col in mgr_cols:
                        col_name = col[0]
                        print(f"  Column: {col_name}")
                        if 'email' in col_name.lower():
                            await cur.execute(f"SELECT COUNT(DISTINCT `{col_name}`) FROM `{table[0]}`")
                            count = await cur.fetchone()
                            print(f"  >>> Distinct {col_name}: {count[0]}")

    conn.close()


asyncio.run(query())

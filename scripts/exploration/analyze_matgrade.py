import asyncio

import asyncmy

from _conn import conn_kwargs


async def analyze():
    conn = await asyncmy.connect(**conn_kwargs())
    async with conn.cursor() as cur:
        await cur.execute('SHOW DATABASES')
        dbs = await cur.fetchall()
        print("Databases:")
        for db in dbs:
            print(f"  {db[0]}")

        # Check for matgrade or ad_service
        for db_name in ['matgrade', 'ad_service']:
            await cur.execute(
                "SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = %s",
                (db_name,),
            )
            if await cur.fetchone():
                print(f"\n=== {db_name} database ===")
                await cur.execute(f'USE `{db_name}`')
                await cur.execute('SHOW TABLES')
                tables = await cur.fetchall()
                for table in tables:
                    print(f"\nTable: {table[0]}")
                    await cur.execute(f'DESCRIBE `{table[0]}`')
                    cols = await cur.fetchall()
                    for col in cols:
                        print(f"  {col[0]} - {col[1]}")

                    # Check for ManagerEmail
                    if 'ManagerEmail' in [col[0] for col in cols]:
                        await cur.execute(f"SELECT COUNT(DISTINCT ManagerEmail) FROM `{table[0]}`")
                        count = await cur.fetchone()
                        print(f"  >>> Distinct ManagerEmail: {count[0]}")

    conn.close()


asyncio.run(analyze())

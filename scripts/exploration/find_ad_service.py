import asyncio

import asyncmy

from _conn import servers


async def find_ad_service():
    for host, port, user, password in servers():
        print(f"\n{'=' * 60}")
        print(f"Checking {host}:{port}")
        print('=' * 60)
        try:
            conn = await asyncmy.connect(host=host, port=port, user=user, password=password)
            async with conn.cursor() as cur:
                await cur.execute("SHOW DATABASES LIKE '%ad%'")
                dbs = await cur.fetchall()

                if dbs:
                    for db in dbs:
                        db_name = db[0]
                        print(f"\nFound: {db_name}")

                        if 'ad_service' in db_name.lower():
                            await cur.execute(f'USE `{db_name}`')
                            await cur.execute('SHOW TABLES')
                            tables = await cur.fetchall()
                            print(f"\nTables in {db_name}:")
                            for tbl in tables:
                                print(f"  - {tbl[0]}")
                                await cur.execute(f'DESCRIBE `{tbl[0]}`')
                                cols = await cur.fetchall()
                                for col in cols:
                                    print(f"      {col[0]} ({col[1]})")
                else:
                    print("No databases with 'ad' found")
            conn.close()
        except Exception as e:
            print(f"Error: {e}")


asyncio.run(find_ad_service())

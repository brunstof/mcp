import asyncio

import asyncmy

from _conn import servers


async def check_databases():
    for host, port, user, password in servers():
        print(f"\n{'=' * 70}")
        print(f"SERVER: {host}:{port}")
        print('=' * 70)
        try:
            conn = await asyncmy.connect(host=host, port=port, user=user, password=password)
            async with conn.cursor() as cur:
                await cur.execute("SHOW DATABASES")
                dbs = await cur.fetchall()

                for db in dbs:
                    db_name = db[0]
                    if db_name in ['information_schema', 'mysql', 'performance_schema', 'sys']:
                        continue

                    print(f"\n[DB] {db_name}")
                    try:
                        await cur.execute(f'USE `{db_name}`')
                        await cur.execute('SHOW TABLES')
                        tables = await cur.fetchall()
                        print(f"   Tables: {len(tables)}")

                        if tables:
                            print(f"   Sample tables: {', '.join([t[0] for t in tables[:5]])}")
                            if len(tables) > 5:
                                print(f"   ... and {len(tables) - 5} more")
                    except Exception as e:
                        print(f"   Error: {str(e)[:50]}")
            conn.close()
            print("[OK] Connected successfully")
        except Exception as e:
            print(f"[FAIL] Connection failed: {e}")


asyncio.run(check_databases())

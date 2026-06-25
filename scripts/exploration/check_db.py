import asyncio

import asyncmy

from _conn import conn_kwargs


async def check_databases():
    conn = await asyncmy.connect(**conn_kwargs())
    async with conn.cursor() as cur:
        await cur.execute('SHOW DATABASES')
        databases = await cur.fetchall()
        print("Available databases:")
        for db in databases:
            print(f"  - {db[0]}")

        # Check for ad_service
        await cur.execute(
            "SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = %s",
            ('ad_service',),
        )
        ad_service = await cur.fetchone()

        if ad_service:
            print("\nFound ad_service database!")
            await cur.execute('USE ad_service')
            await cur.execute('SHOW TABLES')
            tables = await cur.fetchall()
            print("Tables in ad_service:")
            for table in tables:
                print(f"  - {table[0]}")

            # Check for ManagerEmail column
            await cur.execute("""
                SELECT TABLE_NAME, COLUMN_NAME
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = 'ad_service'
                AND COLUMN_NAME LIKE '%Manager%Email%'
            """)
            columns = await cur.fetchall()
            if columns:
                print("\nFound ManagerEmail columns:")
                for col in columns:
                    print(f"  Table: {col[0]}, Column: {col[1]}")

                    # Count distinct ManagerEmail values
                    await cur.execute(f"SELECT COUNT(DISTINCT `{col[1]}`) as count FROM ad_service.`{col[0]}`")
                    count = await cur.fetchone()
                    print(f"  Distinct ManagerEmail count: {count[0]}")
        else:
            print("\nad_service database not found!")

    conn.close()


asyncio.run(check_databases())

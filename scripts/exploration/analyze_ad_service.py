import asyncio

import asyncmy

from _conn import conn_kwargs


async def analyze():
    conn = await asyncmy.connect(**conn_kwargs(db='ad_service'))
    async with conn.cursor() as cur:
        # Count records in each table
        tables = ['adimportous', 'adsettings', 'adusers', 'hrpersonnelinfos']

        print("AD_SERVICE DATABASE STRUCTURE")
        print("=" * 60)

        for table in tables:
            await cur.execute(f'SELECT COUNT(*) FROM {table}')
            count = await cur.fetchone()
            print(f"\n{table.upper()}: {count[0]} records")

        # Check ManagerEmail distinct values
        print("\n" + "=" * 60)
        print("MANAGER EMAIL ANALYSIS")
        print("=" * 60)

        await cur.execute('SELECT COUNT(DISTINCT ManagerEmail) FROM adusers WHERE ManagerEmail IS NOT NULL')
        distinct_count = await cur.fetchone()
        print(f"\nDistinct ManagerEmail values: {distinct_count[0]}")

        await cur.execute('SELECT COUNT(*) FROM adusers WHERE ManagerEmail IS NOT NULL')
        total = await cur.fetchone()
        print(f"Total users with ManagerEmail: {total[0]}")

        await cur.execute('SELECT COUNT(*) FROM adusers WHERE ManagerEmail IS NULL')
        null_count = await cur.fetchone()
        print(f"Users without ManagerEmail: {null_count[0]}")

        # Sample data
        print("\n" + "=" * 60)
        print("SAMPLE MANAGER EMAILS (Top 10)")
        print("=" * 60)
        await cur.execute('SELECT DISTINCT ManagerEmail FROM adusers WHERE ManagerEmail IS NOT NULL LIMIT 10')
        samples = await cur.fetchall()
        for sample in samples:
            print(f"  {sample[0]}")

        # Cost Center analysis
        print("\n" + "=" * 60)
        print("COST CENTER ANALYSIS")
        print("=" * 60)
        await cur.execute('SELECT COUNT(DISTINCT CostCenter) FROM adusers WHERE CostCenter IS NOT NULL')
        cc_count = await cur.fetchone()
        print(f"Distinct Cost Centers: {cc_count[0]}")

    conn.close()


asyncio.run(analyze())

import asyncio

import asyncmy
import matplotlib.pyplot as plt
import pandas as pd

from _conn import conn_kwargs


async def create_diagram():
    conn = await asyncmy.connect(**conn_kwargs(db='ad_service'))
    async with conn.cursor() as cur:
        # Get department distribution
        await cur.execute('''
            SELECT Department, COUNT(*) as Count
            FROM adusers
            WHERE Department IS NOT NULL AND Department != ''
            GROUP BY Department
            ORDER BY Count DESC
            LIMIT 20
        ''')
        data = await cur.fetchall()
    conn.close()

    # Create DataFrame
    df = pd.DataFrame(data, columns=['Department', 'Count'])

    # Create figure with subplots
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8))

    # Bar chart
    ax1.barh(df['Department'], df['Count'], color='steelblue')
    ax1.set_xlabel('Number of Employees', fontsize=12)
    ax1.set_title('Top 20 Departments by Headcount', fontsize=14, fontweight='bold')
    ax1.invert_yaxis()
    for i, v in enumerate(df['Count']):
        ax1.text(v + 50, i, str(v), va='center')

    # Pie chart (top 10)
    top10 = df.head(10)
    colors = plt.cm.Set3(range(len(top10)))
    ax2.pie(top10['Count'], labels=top10['Department'], autopct='%1.1f%%',
            colors=colors, startangle=90)
    ax2.set_title('Top 10 Departments Distribution', fontsize=14, fontweight='bold')

    plt.tight_layout()
    plt.savefig('department_distribution.png', dpi=300, bbox_inches='tight')
    print("\nDiagram saved: department_distribution.png")
    print(f"\nTotal departments analyzed: {len(df)}")
    print(f"Total employees: {df['Count'].sum()}")

    # Print summary
    print("\n" + "=" * 60)
    print("DEPARTMENT DISTRIBUTION SUMMARY")
    print("=" * 60)
    for idx, row in df.iterrows():
        print(f"{row['Department']:<40} {row['Count']:>6}")


asyncio.run(create_diagram())

"""
export_to_csv.py  —  Data Quality Governance Project
Exports all Supabase tables to CSV for Power BI consumption.

Run after control_scorer.py to capture the latest scores.
Then refresh Power BI Desktop to update the dashboard.

Author: Feranmi Okunola
"""

import psycopg2
import pandas as pd
import os
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(
    host=os.getenv("DB_HOST"),
    dbname=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    port=os.getenv("DB_PORT", 5432),
    sslmode="require"
)

BASE = r"C:\Users\flofa\OneDrive\Data Quality Governance Project"

tables = [
    "cde_inventory",
    "control_register",
    "calculated_control_status",
    "score_log",
    "control_score_log",
    "sla_tracker",
]

for table in tables:
    df = pd.read_sql(f"SELECT * FROM {table}", conn)
    path = os.path.join(BASE, f"{table}.csv")
    df.to_csv(path, index=False)
    print(f"Exported {table}: {len(df)} rows → {path}")

conn.close()
print("\nAll exports complete. Open Power BI and click Refresh.")

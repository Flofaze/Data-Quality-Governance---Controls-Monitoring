import pandas as pd
import psycopg2
from dotenv import load_dotenv
import os

load_dotenv()

df = pd.read_csv(r"C:\Users\flofa\OneDrive\Actual Project\data-covenant-initiative\control_register_with_measurements.csv")

conn = psycopg2.connect(
    host=os.getenv("DB_HOST"),
    dbname=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    port=os.getenv("DB_PORT", 5432),
    sslmode="require"
)
cur = conn.cursor()

update_cols = [
    "expected_record_count", "actual_record_count", "completeness_pct",
    "expected_value", "actual_value", "tolerance_pct", "accuracy_variance_pct",
    "expected_arrival_time", "actual_arrival_time", "hours_late"
]

for _, row in df.iterrows():
    vals = [None if pd.isna(row[c]) else row[c] for c in update_cols]
    cur.execute("""
        UPDATE control_register SET
            expected_record_count  = %s,
            actual_record_count    = %s,
            completeness_pct       = %s,
            expected_value         = %s,
            actual_value           = %s,
            tolerance_pct          = %s,
            accuracy_variance_pct  = %s,
            expected_arrival_time  = %s,
            actual_arrival_time    = %s,
            hours_late             = %s
        WHERE control_id = %s
    """, vals + [int(row["control_id"])])

conn.commit()
cur.close()
conn.close()
print("Done — all 351 rows updated")
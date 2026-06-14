"""
simulate_pipeline.py  —  Data Quality Governance Project
Pipeline Simulation Script

Simulates realistic data quality drift between pipeline runs.
Rather than generating completely random values, each run takes the
previous measurement and applies a small random drift — mimicking how
real data quality metrics gradually improve or worsen over time.

v2 changes:
- Wider drift ranges to force threshold boundary crossings
- Per-run directional bias so ~40% of controls worsen each run
- Criticality-weighted drift (Critical CDEs drift more aggressively)

Run order for a full pipeline cycle:
    python simulate_pipeline.py
    python control_scorer.py
    python export_to_csv.py
    Then refresh Power BI

Author: Feranmi Okunola
"""

import os
import random
import psycopg2
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────
# DATABASE CONNECTION
# ─────────────────────────────────────────────
conn = psycopg2.connect(
    host=os.getenv("DB_HOST"),
    dbname=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    port=os.getenv("DB_PORT", 5432),
    sslmode="require"
)
cur = conn.cursor()

# ─────────────────────────────────────────────
# FETCH CURRENT MEASUREMENTS + CRITICALITY
# ─────────────────────────────────────────────
cur.execute("""
    SELECT 
        cr.control_id, 
        cr.dimension, 
        ci.criticality,
        cr.completeness_pct,
        cr.accuracy_variance_pct,
        cr.hours_late,
        cr.expected_record_count,
        cr.expected_value,
        cr.tolerance_pct
    FROM control_register cr
    JOIN cde_inventory ci ON cr.cde_id = ci.cde_id
    ORDER BY cr.control_id
""")
controls = cur.fetchall()
print(f"Fetched {len(controls)} controls from control_register")

# ─────────────────────────────────────────────
# DRIFT SETTINGS — widened to cross thresholds
# ─────────────────────────────────────────────
BASE_COMPLETENESS_DRIFT = 6.0
BASE_ACCURACY_DRIFT     = 4.5
BASE_TIMELINESS_DRIFT   = 2.0

CRITICALITY_MULTIPLIER = {
    "Critical": 1.4,
    "High":     1.1,
    "Medium":   0.8,
}

COMPLETENESS_MIN, COMPLETENESS_MAX = 70.0, 100.0
ACCURACY_MIN,     ACCURACY_MAX     = 0.0,  20.0
TIMELINESS_MIN,   TIMELINESS_MAX   = 0.0,  10.0

# ─────────────────────────────────────────────
# PER-RUN DIRECTIONAL BIAS
# ─────────────────────────────────────────────
def get_bias(control_id):
    seed = int(datetime.now().strftime("%Y%m%d%H")) + control_id
    rng = random.Random(seed)
    return 1 if rng.random() < 0.40 else -1

def drift(current_value, max_drift, min_bound, max_bound, bias, higher_is_worse=False):
    current_float = float(current_value)
    magnitude = random.uniform(max_drift * 0.3, max_drift)
    direction = bias if higher_is_worse else -bias
    new_value = current_float + (direction * magnitude)
    return round(max(min_bound, min(max_bound, new_value)), 2)

# ─────────────────────────────────────────────
# STARTING VALUES FOR FIRST RUN (when NULL)
# ─────────────────────────────────────────────
def starting_completeness(criticality):
    if criticality == "Critical":
        return round(random.uniform(88.0, 99.0), 2)
    elif criticality == "High":
        return round(random.uniform(90.0, 99.5), 2)
    else:
        return round(random.uniform(92.0, 100.0), 2)

def starting_accuracy(criticality):
    if criticality == "Critical":
        return round(random.uniform(0.5, 8.0), 2)
    elif criticality == "High":
        return round(random.uniform(0.3, 6.0), 2)
    else:
        return round(random.uniform(0.1, 4.0), 2)

def starting_timeliness(criticality):
    if criticality == "Critical":
        return round(random.uniform(0.2, 4.0), 2)
    elif criticality == "High":
        return round(random.uniform(0.1, 3.0), 2)
    else:
        return round(random.uniform(0.0, 2.5), 2)

# ─────────────────────────────────────────────
# PROCESS EACH CONTROL
# ─────────────────────────────────────────────
updated = 0
status_preview = {"passing": 0, "partial": 0, "breached": 0}

for row in controls:
    (control_id, dimension, criticality,
     completeness_pct, accuracy_variance_pct, hours_late,
     expected_record_count, expected_value, tolerance_pct) = row

    m = {}
    bias = get_bias(control_id)
    multiplier = CRITICALITY_MULTIPLIER.get(criticality, 1.0)

    if dimension == "Completeness":
        current = float(completeness_pct) if completeness_pct is not None else starting_completeness(criticality)
        new_pct = drift(current, BASE_COMPLETENESS_DRIFT * multiplier, COMPLETENESS_MIN, COMPLETENESS_MAX, bias, higher_is_worse=False)
        expected = int(expected_record_count) if expected_record_count else random.randint(900, 1000)
        actual = int(expected * new_pct / 100)
        m = {
            "expected_record_count": expected, "actual_record_count": actual,
            "completeness_pct": new_pct, "expected_value": None, "actual_value": None,
            "tolerance_pct": None, "accuracy_variance_pct": None,
            "expected_arrival_time": None, "actual_arrival_time": None, "hours_late": None,
        }
        if new_pct >= 98: status_preview["passing"] += 1
        elif new_pct >= 95: status_preview["partial"] += 1
        else: status_preview["breached"] += 1

    elif dimension == "Accuracy":
        current = float(accuracy_variance_pct) if accuracy_variance_pct is not None else starting_accuracy(criticality)
        new_variance = drift(current, BASE_ACCURACY_DRIFT * multiplier, ACCURACY_MIN, ACCURACY_MAX, bias, higher_is_worse=True)
        exp_val = float(expected_value) if expected_value else round(random.uniform(100, 10000), 2)
        tol = float(tolerance_pct) if tolerance_pct else round(random.uniform(0.5, 2.0), 2)
        actual_val = round(exp_val * (1 + new_variance / 100), 2)
        m = {
            "expected_record_count": None, "actual_record_count": None,
            "completeness_pct": None, "expected_value": exp_val, "actual_value": actual_val,
            "tolerance_pct": tol, "accuracy_variance_pct": new_variance,
            "expected_arrival_time": None, "actual_arrival_time": None, "hours_late": None,
        }
        if new_variance < 1: status_preview["passing"] += 1
        elif new_variance < 5: status_preview["partial"] += 1
        else: status_preview["breached"] += 1

    elif dimension == "Timeliness":
        current = float(hours_late) if hours_late is not None else starting_timeliness(criticality)
        new_hours = drift(current, BASE_TIMELINESS_DRIFT * multiplier, TIMELINESS_MIN, TIMELINESS_MAX, bias, higher_is_worse=True)
        base_time = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)
        actual_arrival = base_time + timedelta(hours=new_hours)
        m = {
            "expected_record_count": None, "actual_record_count": None,
            "completeness_pct": None, "expected_value": None, "actual_value": None,
            "tolerance_pct": None, "accuracy_variance_pct": None,
            "expected_arrival_time": base_time.strftime("%H:%M:%S"),
            "actual_arrival_time": actual_arrival.strftime("%H:%M:%S"),
            "hours_late": new_hours,
        }
        if new_hours <= 0.5: status_preview["passing"] += 1
        elif new_hours <= 2: status_preview["partial"] += 1
        else: status_preview["breached"] += 1

    else:
        continue

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
    """, (
        m["expected_record_count"], m["actual_record_count"], m["completeness_pct"],
        m["expected_value"], m["actual_value"], m["tolerance_pct"],
        m["accuracy_variance_pct"], m["expected_arrival_time"],
        m["actual_arrival_time"], m["hours_late"], control_id
    ))
    updated += 1

conn.commit()
cur.close()
conn.close()

total = sum(status_preview.values())
print(f"\nDone — {updated} controls updated with drifted measurements")
print(f"\nEstimated status distribution this run:")
print(f"  Passing  : {status_preview['passing']:>3} ({round(status_preview['passing']/total*100,1)}%)")
print(f"  Partial  : {status_preview['partial']:>3} ({round(status_preview['partial']/total*100,1)}%)")
print(f"  Breached : {status_preview['breached']:>3} ({round(status_preview['breached']/total*100,1)}%)")
print(f"\nNext steps:")
print(f"  1. python control_scorer.py")
print(f"  2. python export_to_csv.py")
print(f"  3. Refresh Power BI")
print(f"  4. Execute WF2 in n8n to detect new breaches")

"""
control_scorer.py  —  Data Quality Governance Project
Dimensions : Completeness (BCBS 239 P4) · Accuracy (BCBS 239 P3) · Timeliness (BCBS 239 P6)
Ownership  : ITSO (IT System Owner) · BUSO (Business Unit System Owner)
SLA Tiers  : Derived from DAMA-DMBOK2 criticality x dimension
Author     : Feranmi Okunola
"""

import os
import psycopg2
from dotenv import load_dotenv
from datetime import date, timedelta

load_dotenv()

conn = psycopg2.connect(
    host=os.getenv("DB_HOST"),
    dbname=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    port=os.getenv("DB_PORT", 5432),
    sslmode="require",
)
cur = conn.cursor()
print("Connected to Supabase successfully.")

# ── Load CDEs and controls ────────────────────────────────────────────────────
cur.execute("SELECT * FROM cde_inventory")
cde_cols = [d[0] for d in cur.description]
cdes = [dict(zip(cde_cols, r)) for r in cur.fetchall()]

cur.execute("""
    SELECT 
        control_id, cde_id, cde_name, division, system_name,
        dimension, control_type,
        calculated_status AS control_status
    FROM calculated_control_status
""")
ctrl_cols = [d[0] for d in cur.description]
controls = [dict(zip(ctrl_cols, r)) for r in cur.fetchall()]
print(f"Loaded {len(cdes)} CDEs and {len(controls)} controls.")

today = date.today()

# ── SLA tiers (DAMA-DMBOK2 criticality x dimension) ──────────────────────────
SLA_TIERS = {
    "Critical": {"Completeness": 3, "Accuracy": 5, "Timeliness": 7},
    "High":     {"Completeness": 5, "Accuracy": 7, "Timeliness": 10},
    "Medium":   {"Completeness": 7, "Accuracy": 10, "Timeliness": 14},
}

# ── Dimension weights (BCBS 239 priority) ────────────────────────────────────
DIMENSION_WEIGHTS = {"Completeness": 0.35, "Accuracy": 0.35, "Timeliness": 0.30}

# ── Control scoring rules ─────────────────────────────────────────────────────
# Each control is evaluated: Passing=100, Partial=60, Breached=0, Missing=0
# Missing is worse than Breached — no control at all is a hard governance failure

STATUS_SCORES = {"Passing": 100, "Partial": 60, "Breached": 0, "Missing": 0}

HARD_BREACH_CONDITIONS = [
    # Any Critical CDE with a Missing Completeness control = automatic High Risk
    lambda ctrl, cde: (
        cde["criticality"] == "Critical"
        and ctrl["dimension"] == "Completeness"
        and ctrl["control_status"] == "Missing"
    ),
    # Any CDE with both Accuracy AND Completeness controls Breached simultaneously
    # (checked at CDE level below)
]


def score_cde(cde, cde_controls):
    """Score one CDE across all three dimensions. Returns overall score + risk classification."""
    dimension_scores = {}
    hard_breach = False

    for ctrl in cde_controls:
        dim = ctrl["dimension"]
        status = ctrl["control_status"]
        raw = STATUS_SCORES.get(status, 0)

        # Hard breach: Critical CDE with Missing Completeness control
        if cde["criticality"] == "Critical" and dim == "Completeness" and status == "Missing":
            hard_breach = True

        dimension_scores[dim] = raw

    # Hard breach: both Completeness and Accuracy breached on same CDE
    comp_status = next((c["control_status"] for c in cde_controls if c["dimension"] == "Completeness"), "Missing")
    acc_status  = next((c["control_status"] for c in cde_controls if c["dimension"] == "Accuracy"),  "Missing")
    if comp_status in ("Breached", "Missing") and acc_status in ("Breached", "Missing"):
        hard_breach = True

    # Weighted overall score
    overall = sum(
        dimension_scores.get(dim, 0) * weight
        for dim, weight in DIMENSION_WEIGHTS.items()
    )
    overall = round(overall, 2)

    if hard_breach:
        risk = "High Risk"
    elif overall >= 75:
        risk = "Low Risk"
    elif overall >= 45:
        risk = "Medium Risk"
    else:
        risk = "High Risk"

    return overall, risk, dimension_scores, hard_breach


# ── Main scoring loop ─────────────────────────────────────────────────────────
scoring_results = []
new_sla_records = []

for cde in cdes:
    cid = cde["cde_id"]
    cde_controls = [c for c in controls if c["cde_id"] == cid]

    overall, risk, dim_scores, hard_breach = score_cde(cde, cde_controls)

    scoring_results.append({
        "cde_id":             cid,
        "cde_name":           cde["cde_name"],
        "division":           cde["division"],
        "criticality":        cde["criticality"],
        "overall_score":      overall,
        "completeness_score": dim_scores.get("Completeness", 0),
        "accuracy_score":     dim_scores.get("Accuracy", 0),
        "timeliness_score":   dim_scores.get("Timeliness", 0),
        "risk_classification": risk,
        "hard_breach_override": hard_breach,
    })

    # Write results to score_log
    cur.execute("""
        INSERT INTO score_log
            (cde_id, run_date, completeness_score, accuracy_score, timeliness_score,
             overall_score, risk_classification, hard_breach_override)
        VALUES (%s, NOW(), %s, %s, %s, %s, %s, %s)
    """, (
        cid,
        dim_scores.get("Completeness", 0),
        dim_scores.get("Accuracy", 0),
        dim_scores.get("Timeliness", 0),
        overall, risk, hard_breach,
    ))

    # Write rule-level log
    for ctrl in cde_controls:
        cur.execute("""
            INSERT INTO control_score_log
                (control_id, cde_id, run_date, dimension, control_type,
                 control_status, raw_score, dimension_weight, weighted_contrib)
            VALUES (%s, %s, NOW(), %s, %s, %s, %s, %s, %s)
        """, (
            ctrl["control_id"], cid,
            ctrl["dimension"], ctrl["control_type"], ctrl["control_status"],
            STATUS_SCORES.get(ctrl["control_status"], 0),
            DIMENSION_WEIGHTS.get(ctrl["dimension"], 0),
            round(STATUS_SCORES.get(ctrl["control_status"], 0) * DIMENSION_WEIGHTS.get(ctrl["dimension"], 0), 2),
        ))

    # Generate SLA records for breached/missing controls not yet tracked
    for ctrl in cde_controls:
        if ctrl["control_status"] in ("Breached", "Missing"):
            cur.execute(
                "SELECT 1 FROM sla_tracker WHERE control_id = %s AND status != 'Resolved'",
                (ctrl["control_id"],)
            )
            if cur.fetchone():
                continue

            criticality = cde["criticality"]
            dimension   = ctrl["dimension"]
            sla_days    = SLA_TIERS[criticality][dimension]
            breach_date = today
            sla_deadline = breach_date + timedelta(days=sla_days)

            cur.execute("""
                INSERT INTO sla_tracker
                    (control_id, cde_id, cde_name, dataset_name, system_name, division,
                     dimension, control_status, criticality, sla_days,
                     breach_date, sla_deadline,
                     buso_email, buso_manager_email, itso_email, itso_manager_email,
                     first_alert_sent, escalation_sent, status)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,FALSE,FALSE,'Open')
            """, (
                ctrl["control_id"], cid, cde["cde_name"],
                cde["dataset_name"], cde["system_name"], cde["division"],
                dimension, ctrl["control_status"], criticality, sla_days,
                breach_date, sla_deadline,
                cde["buso_email"], cde["buso_manager_email"],
                cde["itso_email"], cde["itso_manager_email"],
            ))

conn.commit()

# ── Summary report ────────────────────────────────────────────────────────────
total = len(scoring_results)
high  = sum(1 for r in scoring_results if r["risk_classification"] == "High Risk")
med   = sum(1 for r in scoring_results if r["risk_classification"] == "Medium Risk")
low   = sum(1 for r in scoring_results if r["risk_classification"] == "Low Risk")
hbo   = sum(1 for r in scoring_results if r["hard_breach_override"])

print("\n── Scoring Complete ──────────────────────────────────────")
print(f"  Total CDEs scored : {total}")
print(f"  High Risk         : {high}  ({round(high/total*100,1)}%)")
print(f"  Medium Risk       : {med}   ({round(med/total*100,1)}%)")
print(f"  Low Risk          : {low}  ({round(low/total*100,1)}%)")
print(f"  Hard breach overrides : {hbo}")
print("─────────────────────────────────────────────────────────")

cur.close()
conn.close()
print("Done. Results written to score_log, control_score_log, and sla_tracker.")

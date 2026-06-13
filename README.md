# Data Quality Governance Project
### Data Governance Controls Monitoring System

**Author:** Feranmi Okunola — Data Governance Analyst, Operations Risks and Regulatory Control, Morgan Stanley UK (Glasgow)

---

## Project Overview

The Data Quality Governance Project is an end-to-end automated data governance controls monitoring system built to demonstrate real-world application of BCBS 239, DAMA-DMBOK2, and enterprise data governance frameworks.

The system monitors **117 Critical Data Elements (CDEs)** across **5 divisions** and **15 IT systems**, automatically scoring controls, detecting breaches, escalating to data owners, and surfacing insights through a Power BI dashboard — all driven by a self-hosted n8n automation layer and a Supabase PostgreSQL backend.

> All data in this project is synthetic and fictional. The test domain `@meridianbank.com` is used throughout. No real Financial Organisation data is included.

---

## Business Context

Under **BCBS 239** (Basel Committee on Banking Supervision Principles for Effective Risk Data Aggregation and Risk Reporting), financial institutions must demonstrate — not just assert — that their critical data is accurate, complete, and timely. Manual tracking of 351 controls across 117 CDEs is operationally unsustainable at scale.

This project addresses that gap by automating:
- Evidence-based control status calculation from actual measurements
- Risk scoring with hard breach overrides for critical CDEs
- SLA breach detection and stakeholder notification
- Escalation to managers when SLA deadlines are missed
- Weekly governance digest reporting to senior stakeholders
- Closure confirmation when breaches are resolved

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Database | Supabase (PostgreSQL) — eu-west-2 London |
| Automation | n8n self-hosted v2.14.2 |
| Scoring Engine | Python (psycopg2, pandas) |
| Dashboard | Power BI Desktop |
| Email | Gmail OAuth2 |
| Dataset | Excel (117 CDEs, 351 controls, 173 SLA records) |

---

## System Architecture

```
┌─────────────────────────────────────────────────────┐
│                   SUPABASE (PostgreSQL)              │
│  Tables: cde_inventory, control_register,           │
│          score_log, control_score_log, sla_tracker  │
│  View:   calculated_control_status                  │
└──────────────┬──────────────────────────────────────┘
               │
       ┌───────▼────────┐
       │  Python Scripts │
       │  simulate_pipeline.py   → Drifts measurements between runs
       │  control_scorer.py      → Calculates risk scores from view
       │  export_to_csv.py       → Exports to CSV for Power BI
       │  update_measurements.py → Updates measurement columns
       │  generate_excel_report.py → Generates Excel report
       └───────┬────────┘
               │
       ┌───────▼────────┐
       │   n8n Workflows │
       │  WF1  → Trigger Python Scorer (scheduled Sunday 07:00)
       │  WF2  → Draft Breach Alert Digest (scheduled 08:00)
       │  WF2B → Approval Gate — reply SEND to dispatch alerts
       │  WF3  → SLA Escalation to managers (scheduled daily)
       │  WF4  → Weekly Governance Digest (scheduled Monday 08:00)
       │  WF5  → Closure Confirmation (scheduled daily 09:00)
       └───────┬────────┘
               │
       ┌───────▼────────┐
       │   Power BI      │
       │  6-page dashboard consuming CSV exports
       │  Pages: Governance Overview, Control Register,
       │         SLA Tracker, CDE Drillthrough,
       │         Control Breach Heatmap,
       │         Measurements Behind Status
       └────────────────┘
```

---

## Dataset Structure

| Table | Rows | Description |
|-------|------|-------------|
| cde_inventory | 117 | Critical Data Elements across 5 divisions |
| control_register | 351 | 3 controls per CDE (Completeness, Accuracy, Timeliness) |
| sla_tracker | 173 | SLA records with breach dates and deadlines |
| score_log | Growing | CDE-level risk scores per scorer run |
| control_score_log | Growing | Control-level scores per scorer run |

**Divisions:** Finance, Investment Management, LCD, Operations, Wealth Management

**IT Systems:** 15 systems including General Ledger System, Compliance Monitoring Platform, Regulatory Reporting System, Treasury Management System, and others

**Criticality:** Critical (30%), High (40%), Medium (30%) — assigned via weighted random, acknowledged as a limitation. Real implementation would use formal scoring: regulatory impact + financial materiality + operational dependency.

---

## Scoring Engine

### Control Status (calculated_control_status view)

Status is derived from actual measurements — not manually assigned assertions. This directly implements **BCBS 239 Principle 3** (accuracy must be demonstrated).

| Dimension | Passing | Partial | Breached |
|-----------|---------|---------|----------|
| Completeness | ≥98% | 95–97.9% | <95% |
| Accuracy variance | <1% | 1–5% | >5% |
| Timeliness | ≤0.5hrs late | 0.5–2hrs | >2hrs |

### Risk Scoring (control_scorer.py)

| Parameter | Value |
|-----------|-------|
| Completeness weight | 0.35 |
| Accuracy weight | 0.35 |
| Timeliness weight | 0.30 |
| Passing score | 100 |
| Partial score | 60 |
| Breached/Missing score | 0 |

**SLA Tiers:**

| Criticality | Completeness SLA | Accuracy SLA | Timeliness SLA |
|-------------|-----------------|--------------|----------------|
| Critical | 3 days | 5 days | 7 days |
| High | 5 days | 7 days | 10 days |
| Medium | 7 days | 10 days | 14 days |

**Risk Classification:**

| Score | Classification |
|-------|---------------|
| ≥75 | Low Risk |
| ≥45 | Medium Risk |
| <45 | High Risk |

**Hard Breach Overrides:** A CDE is automatically classified as High Risk if it is Critical criticality with Missing Completeness, or if both Completeness and Accuracy are Breached simultaneously.

**Scorer Results (as of initial run):** 61 High Risk (52.1%), 41 Medium Risk (35%), 15 Low Risk (12.8%), 34 hard breach overrides

---

## n8n Workflow Details

### WF2 — Breach Alert Digest
Scheduled daily at 08:00. Queries `pending_first_alerts` view and builds a single HTML digest email listing all active breaches. Creates a Gmail draft for human review before dispatch.

### WF2B — Approval Gate
Triggered by replying **SEND** to the digest draft. Dispatches individual breach notification emails to `buso_email` (To) and `itso_email` (CC) for each pending breach. Stamps `alert_sent_date` on dispatch. Implements human-in-the-loop control — a deliberate design decision reflecting real regulated-environment practice where automated mass emails require governance sign-off.

### WF3 — SLA Escalation
Scheduled daily. Fires when `sla_deadline < CURRENT_DATE` and `first_alert_sent = TRUE` and `escalation_sent = FALSE`. Sends escalation emails to direct owners and CCs both BUSO and ITSO managers (`buso_manager_email`, `itso_manager_email`).

### WF4 — Weekly Governance Digest
Scheduled Monday 08:00. Aggregates breach counts and average scores by division from `control_score_log` and sends a single HTML summary table to governance stakeholders.

### WF5 — Closure Confirmation
Scheduled daily 09:00. Detects records where `status = 'Resolved'` and `resolution_date = CURRENT_DATE` and sends closure confirmation emails to data owners.

---

## Power BI Dashboard

Data source: CSV exports via `export_to_csv.py` (direct PostgreSQL connection not used due to SSL limitations on the Supabase eu-west-2 pooler).

**Refresh process:** Run `simulate_pipeline.py` → Run `control_scorer.py` → Run `export_to_csv.py` → Refresh in Power BI Desktop.

| Page | Purpose |
|------|---------|
| Governance Overview | KPI cards, avg score by division, control status donut |
| Control Register | Full control table with RAG status, 4 slicers |
| SLA Tracker | Overdue breaches, filterable by division and status |
| CDE Drillthrough | Per-CDE score history from score_log |
| Control Breach Heatmap | RAG matrix (dimension × division), breach count by system |
| Measurements Behind Status | Evidence layer — completeness %, accuracy variance, hours late by division with threshold reference lines |

---

## Key Design Decisions

**1. Evidence-based status calculation**
Original dataset used manually assigned control statuses. Upgraded to a `calculated_control_status` SQL view using CASE WHEN thresholds against 9 measurement columns. This makes every breach defensible — status is derived from data, not opinion.

**2. Human-in-the-loop approval gate**
WF2B requires a human to reply SEND before breach alerts are dispatched. This mirrors real governance practice where automated notifications to senior stakeholders require review. Removes the risk of false-positive mass emails.

**3. Digest-first, individual-second pattern**
WF2 creates one digest draft (not 173 individual drafts) to prevent Gmail rate limiting and give the reviewer a single consolidated view before approving dispatch.

**4. CSV export workaround for Power BI**
Direct PostgreSQL connection to Supabase eu-west-2 pooler fails due to SSL certificate issues in Power BI Desktop. Resolved via Python CSV export — a pragmatic workaround that also creates an audit trail of each data snapshot.

**5. Separation of sla_id and cde_id**
A key architectural lesson: `sla_id` and `cde_id` are not interchangeable. `sla_tracker` maps multiple SLA records per CDE (one per control dimension). Treating them as equivalent caused silent query failures in early workflow testing.

**6. Scorer reads from calculated_control_status view**
Original implementation read `control_status` directly from `control_register` — a static column that never updated between runs. Updated to read `calculated_status` from the `calculated_control_status` view, ensuring scores reflect live measurement drift generated by `simulate_pipeline.py` on every pipeline cycle.

---

## BCBS 239 Alignment

| Principle | Implementation |
|-----------|---------------|
| Principle 3 — Accuracy | Calculated status from measurements, not assertions |
| Principle 4 — Completeness | Completeness % tracked per CDE with 98% threshold |
| Principle 6 — Timeliness | Hours late tracked with 0.5hr passing threshold |
| Principle 11 — Accuracy of Reports | Risk scoring and hard breach overrides for critical CDEs |

---

## Repository Structure

```
data-governance-controls-monitoring/
├── control_scorer.py                        # Risk scoring engine
├── simulate_pipeline.py                     # Drift-based pipeline simulation
├── export_to_csv.py                         # Supabase → CSV export for Power BI
├── update_measurements.py                   # Updates measurement columns in control_register
├── generate_excel_report.py                 # Generates Excel governance report
├── Data_Governance_Project_Dataset_v1.xlsx # Source dataset
├── Data_Governance_Report.xlsx              # Generated Excel report
├── .gitignore                               # Excludes .env and credentials
└── README.md                                # This file
```

---

## Setup

### Prerequisites
- Python 3.9+
- Supabase account with PostgreSQL access
- n8n self-hosted instance
- Power BI Desktop
- Gmail account with OAuth2 credentials

### Environment Variables
Create a `.env` file in the project root:

```
DB_HOST=your-supabase-host
DB_NAME=postgres
DB_USER=postgres.your-project-id
DB_PASSWORD=your-password
DB_PORT=5432
```

### Running the Full Pipeline
```bash
pip install psycopg2-binary pandas python-dotenv
python simulate_pipeline.py   # Drift measurements
python control_scorer.py      # Score CDEs and write to score_log
python export_to_csv.py       # Export to CSV for Power BI
# Then open Power BI Desktop and click Refresh
```

---

## Limitations and Future Improvements

- **Criticality assignment** is currently random-weighted. Production implementation would use formal scoring against regulatory impact, financial materiality, and operational dependency
- **WF1 SSH trigger** is a placeholder — requires OpenSSH to be enabled on the host machine for full automation
- **Score trend line chart** in CDE Drillthrough will become more meaningful as weekly scorer runs accumulate over time
- **Power BI SSL workaround** — direct database connection would replace CSV exports in a production environment with proper network configuration
- **Risk classification stability** — hard breach overrides lock a significant proportion of CDEs into High Risk regardless of measurement drift. A production system would use a more granular override hierarchy tied to specific remediation states

---

## Portfolio Context

This project was built to demonstrate end-to-end data governance engineering capability in a realistic financial services context. It deliberately mirrors real Data Governance function workflows including BCBS 239 compliance, Data Management and cataloguing concepts, stakeholder notification chains, and evidence-based control monitoring.

# Resume Pipeline

Automated resume processing pipeline: from raw PDF to hiring decision.

Extracts text from PDF resumes, detects and redacts PII, scores each resume against a job description using GPT-4o-mini, and builds an analytics layer with dbt + DuckDB.

## What This Project Demonstrates

- **ETL Pipeline** — Extract → Transform → Load, classic data engineering pattern
- **LLM as a Judge** — GPT evaluates unstructured data and returns structured JSON (score, recommendation, reasoning)
- **Preprocessing Impact** — dirty resume with PII gets lower score not because of PII itself, but because poor content quality (garbage in = garbage out)
- **dbt + DuckDB Analytics** — staging → mart SQL pattern, turning raw LLM output into business-ready tables
- **Orchestration** — Airflow DAG with task dependencies, retries, and monitoring

## Architecture

```
resume-pipeline/
├── dags/
│   └── resume_dag.py               — Airflow DAG (3 tasks) + standalone mode
├── scripts/
│   └── extract.py                  — PDF → JSON (pdfplumber, PII detection, sections)
├── score.py                        — GPT-4o-mini scoring vs job description
├── run_dbt.py                      — runs dbt, then queries DuckDB results
├── dbt_project/
│   ├── dbt_project.yml             — dbt config (materialized: table)
│   ├── profiles.yml                — DuckDB adapter config
│   └── models/
│       ├── sources.yml             — JSON sources declaration
│       ├── stg_resumes.sql         — staging: rename + select from JSON
│       └── mart_resumes.sql        — mart: JOIN scores + derived metrics
├── data/
│   ├── resumes/                    — 6 sample PDF resumes
│   ├── *.json                      — generated pipeline output (gitignored)
│   └── resume_analytics.duckdb    — generated DuckDB file (gitignored)
├── docker-compose.yml              — Airflow + Postgres (Docker)
├── requirements.txt                — local dependencies
└── requirements-airflow.txt        — dependencies inside Docker
```

## Pipeline Flow

```
6 PDF resumes
     ↓
[Task 1] Extract (pdfplumber)
     → parse text, detect sections (experience, education, skills)
     → find PII (email, phone, SSN, address, salary, driver license)
     → raw_extracted.json
     ↓
[Task 2] Preprocess (PII redact + normalize)
     → replace PII: john@email.com → [EMAIL], 456-78-9012 → [SSN]
     → remove boilerplate: "Page 1 of 3", "Confidential"
     → fix unicode: smart quotes, dashes, bullets
     → preprocessed_resumes.json
     ↓
[Task 3] Score (GPT-4o-mini)
     → evaluate each resume against job description (Senior Python Engineer)
     → returns: score 0-100, recommendation, strengths, weaknesses
     → scored_resumes.json
     ↓
[dbt] Transform (DuckDB)
     → stg_resumes: JSON → clean SQL table (rename, select)
     → mart_resumes: JOIN preprocessing + scores, add derived metrics:
        - pii_risk_level: HIGH_RISK (>5 PII) / MEDIUM_RISK / CLEAN
        - cleaning_impact: HEAVILY_CLEANED / MODERATELY_CLEANED / MINIMAL
     → resume_analytics.duckdb
```
**Flow:** PDF resumes → Extract → Preprocess (clean + PII redact) → Score with LLM

Two ways to run: standalone Python script or full Airflow orchestration.

## Quick Start (standalone — no Airflow)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set your OpenAI key
cp .env.example .env
# edit .env → OPENAI_KEY=sk-your-key

# 3. Run full pipeline
python dags/resume_dag.py

# 4. Run dbt analytics
# 1. Run full pipeline
python dags/resume_dag.py

# 2. View analytics in DuckDB
python run_dbt.py
```

## Airflow Mode (Docker)

```bash
# 1. Set your OpenAI key
cp .env.example .env
# edit .env → OPENAI_KEY=sk-your-key

# 2. Start Airflow
docker compose up -d

# 3. Wait ~30 sec, open UI
open http://localhost:8080
# Login: admin / admin

# 4. Find "resume_processing_pipeline" DAG → trigger it

# 5. Stop when done
docker compose down
```

### What you see in Airflow UI:
- **DAG graph**: `extract_resumes → preprocess_resumes → score_with_llm`
- **Each task**: green (success), red (failed), yellow (running)
- **Logs**: click any task → Log → see full output
- **Retry**: if a task fails, Airflow retries 2 times automatically

## Sample Resumes

| File | Problem | PII Count | LLM Score |
|------|---------|-----------|-----------|
| `01_clean_resume.pdf` | None (baseline) | 2 | 92 — strong_yes |
| `02_dirty_encoding_resume.pdf` | Smart quotes, boilerplate | 2 | 55 — maybe |
| `03_pii_heavy_resume.pdf` | SSN, DOB, address, salary, references | **15** | 10 — no |
| `04_very_long_resume.pdf` | Verbose (5 pages worth) | 9 | 85 — yes |
| `05_noisy_boilerplate_resume.pdf` | ATS system headers/metadata | 4 | 75 — maybe |
| `06_minimal_resume.pdf` | Too little info | 1 | 20 — no |

## dbt Analytics

After pipeline completes, `run_dbt.py` executes real dbt models and queries the results:

```
MART: mart_resumes
resume_file              score  recommendation  pii_risk_level  cleaning_impact
01_clean_resume.pdf         92  strong_yes      MEDIUM_RISK     MINIMAL_CHANGES
04_very_long_resume.pdf     85  yes             HIGH_RISK       MINIMAL_CHANGES
05_noisy_boilerplate.pdf    75  maybe           MEDIUM_RISK     MODERATELY_CLEANED
02_dirty_encoding.pdf       55  maybe           MEDIUM_RISK     MODERATELY_CLEANED
06_minimal_resume.pdf       20  no              MEDIUM_RISK     MINIMAL_CHANGES
03_pii_heavy_resume.pdf     10  no              HIGH_RISK       MODERATELY_CLEANED
```
## Structure

```
resume-pipeline/
├── dags/
│   └── resume_dag.py           # Airflow DAG (works standalone too)
├── scripts/
│   └── extract.py              # PDF → clean text + PII redaction
├── score.py                    # LLM scoring (GPT-4o-mini)
├── run_dbt.py                  # DuckDB analytics (staging → mart)
├── dbt_project/
│   └── models/
│       ├── stg_resumes.sql     # Raw staging
│       └── mart_resumes.sql    # Scored + enriched
├── data/
│   └── resumes/                # 6 sample PDFs
├── docker-compose.yml          # Airflow + Postgres
├── requirements.txt            # Local dependencies
├── requirements-airflow.txt    # Dependencies inside Docker
└── .env.example
```

## Sample Resumes

| File | Problem | PII Count |
|------|---------|-----------|
| `01_clean_resume.pdf` | None (baseline) | 2 |
| `02_dirty_encoding_resume.pdf` | Smart quotes, boilerplate | 2 |
| `03_pii_heavy_resume.pdf` | SSN, DOB, address, salary, references | **15** |
| `04_very_long_resume.pdf` | Verbose (5 pages worth) | 9 |
| `05_noisy_boilerplate_resume.pdf` | ATS system headers/metadata | 4 |
| `06_minimal_resume.pdf` | Too little info | 1 |

## Why Airflow?

Without Airflow (script): run manually, no retry, no monitoring.

With Airflow:
- **Schedule**: run every day at 6am automatically
- **Retry**: if OpenAI API times out → retry 2x with 2min delay
- **Monitoring**: UI shows which step failed and why
- **Alerting**: Slack/email when pipeline breaks
- **History**: see all past runs, duration, success rate

## Why dbt + DuckDB?

Without dbt: Python script with raw SQL, hardcoded paths, you manage execution order.

With dbt:
- `{{ source() }}` and `{{ ref() }}` — dbt knows data dependencies, builds DAG
- `dbt run` — executes models in correct order automatically
- SQL files in `models/` — easy to read, test, and extend
- In production: same pattern with BigQuery/Snowflake/Postgres instead of DuckDB

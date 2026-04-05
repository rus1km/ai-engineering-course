"""
Airflow DAG for Resume Processing Pipeline.

Flow: Extract PDFs → Preprocess (clean + PII redact) → Score with LLM

Works in two modes:
  1. Airflow: docker compose up → http://localhost:8080 → trigger DAG
  2. Standalone: python dags/resume_dag.py
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path


def _get_base_dir():
    """Resolve base directory — works in Docker and locally."""
    # In Docker: /opt/airflow/
    if Path("/opt/airflow/data").exists():
        return Path("/opt/airflow")
    # Local: parent of dags/
    return Path(__file__).parent.parent


BASE_DIR = _get_base_dir()
RESUMES_DIR = str(BASE_DIR / "data" / "resumes")
OUTPUT_DIR = str(BASE_DIR / "data")


def _add_to_path():
    """Add scripts dir to path for imports."""
    scripts_dir = str(BASE_DIR / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    base = str(BASE_DIR)
    if base not in sys.path:
        sys.path.insert(0, base)


# ---------------------------------------------------------------------------
# Task functions
# ---------------------------------------------------------------------------


def task_extract(**kwargs):
    """Task 1: Extract raw text from PDF resumes."""
    _add_to_path()
    from extract import process_all_resumes

    results = process_all_resumes(RESUMES_DIR, redact=False)

    output_path = os.path.join(OUTPUT_DIR, "raw_extracted.json")
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    total_pii = sum(r["pii_total"] for r in results)
    print(f"Extracted {len(results)} resumes, found {total_pii} PII items")
    print(f"Output: {output_path}")
    return output_path


def task_preprocess(**kwargs):
    """Task 2: Clean text, normalize, redact PII."""
    _add_to_path()
    from extract import process_all_resumes

    results = process_all_resumes(RESUMES_DIR, redact=True)

    output_path = os.path.join(OUTPUT_DIR, "preprocessed_resumes.json")
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    total_pii = sum(r["pii_total"] for r in results)
    print(f"Preprocessed {len(results)} resumes, redacted {total_pii} PII items")
    print(f"Output: {output_path}")
    return output_path


def task_score(**kwargs):
    """Task 3: Score each resume against job description with LLM."""
    _add_to_path()
    from score import score_resume, JOB_DESCRIPTION  # also loads .env

    api_key = os.environ.get("OPENAI_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("WARNING: No OPENAI_KEY — skipping LLM scoring")
        return None

    input_path = os.path.join(OUTPUT_DIR, "preprocessed_resumes.json")
    with open(input_path) as f:
        resumes = json.load(f)

    scored = []
    for r in resumes:
        result = score_resume(r["text"], JOB_DESCRIPTION, api_key)
        scored.append({**r, "score": result})
        s = result.get("score", "?")
        rec = result.get("recommendation", "?")
        print(f"  {r['file']}: {s}/100 ({rec})")

    output_path = os.path.join(OUTPUT_DIR, "scored_resumes.json")
    with open(output_path, "w") as f:
        json.dump(scored, f, indent=2)

    print(f"Scored {len(scored)} resumes -> {output_path}")
    return output_path


# ---------------------------------------------------------------------------
# Airflow DAG (only when Airflow is installed)
# ---------------------------------------------------------------------------

try:
    from airflow import DAG
    from airflow.operators.python import PythonOperator

    default_args = {
        "owner": "ai-engineering-course",
        "depends_on_past": False,
        "start_date": datetime(2024, 1, 1),
        "retries": 2,
        "retry_delay": timedelta(minutes=2),
    }

    with DAG(
        dag_id="resume_processing_pipeline",
        default_args=default_args,
        description="Extract → Preprocess → Score resumes with LLM",
        schedule=None,  # Manual trigger
        catchup=False,
        tags=["ai-engineering", "preprocessing", "llm"],
    ) as dag:

        t1 = PythonOperator(
            task_id="extract_resumes",
            python_callable=task_extract,
        )

        t2 = PythonOperator(
            task_id="preprocess_resumes",
            python_callable=task_preprocess,
        )

        t3 = PythonOperator(
            task_id="score_with_llm",
            python_callable=task_score,
        )

        t1 >> t2 >> t3

except ImportError:
    pass  # Airflow not installed — standalone mode


# ---------------------------------------------------------------------------
# Standalone execution
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("RESUME PIPELINE (standalone mode)")
    print("=" * 60)

    print("\n[1/3] Extracting resumes from PDF...")
    task_extract()

    print("\n[2/3] Preprocessing (clean + PII redaction)...")
    task_preprocess()

    print("\n[3/3] Scoring with LLM...")
    task_score()

    print("\n" + "=" * 60)
    print("Pipeline complete!")
    print("Run 'python run_dbt.py' for DuckDB analytics.")
    print("=" * 60)

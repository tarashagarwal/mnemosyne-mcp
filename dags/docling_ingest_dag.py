import sys
import os
from pathlib import Path

# Add the dags directory to Python path for imports
dags_dir = Path(__file__).parent
if str(dags_dir) not in sys.path:
    sys.path.insert(0, str(dags_dir))

from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime
from extract_pages import extract_pdf_pages

# Paths relative to project root
PDF_PATH = "docs/future_queen.pdf"
BOOK_NAME = "future_queen"

default_args = {
    "owner": "airflow",
    "retries": 0
}

with DAG(
    dag_id="docling_pdf_page_ingestion",
    default_args=default_args,
    start_date=datetime(2024, 1, 1),
    schedule_interval=None,
    catchup=False,
    tags=["docling", "pdf", "mcp"]
) as dag:

    extract_task = PythonOperator(
        task_id="extract_pdf_pages",
        python_callable=extract_pdf_pages,
        op_kwargs={
            "pdf_path": PDF_PATH,
            "book_name": BOOK_NAME
        }
    )

    extract_task

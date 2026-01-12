import sys
import os
import json
from pathlib import Path

# Add the dags directory to Python path for imports
dags_dir = Path(__file__).parent
if str(dags_dir) not in sys.path:
    sys.path.insert(0, str(dags_dir))

from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime
from extract_chunks import extract_pdf_chunks
from process_chunks import process_chunks
from mark_book_available import mark_book_available
# Load books from books.json
project_root = Path(__file__).parent.parent
books_json_path = project_root / "docs" / "books.json"

try:
    with open(books_json_path, 'r') as f:
        books_data = json.load(f)
    books = books_data.get("books", [])
except FileNotFoundError:
    print(f"Warning: books.json not found at {books_json_path}")
    books = []
except json.JSONDecodeError as e:
    print(f"Error parsing books.json: {e}")
    books = []

default_args = {
    "owner": "airflow",
    "retries": 0
}

def normalize_book_name(file_name: str) -> str:
    """Convert file name to book name (remove extension, replace underscores/hyphens)"""
    return Path(file_name).stem.replace("_", "_").lower()

with DAG(
    dag_id="docling_pdf_page_ingestion",
    default_args=default_args,
    start_date=datetime(2024, 1, 1),
    schedule_interval=None,
    catchup=False,
    tags=["docling", "pdf", "mcp"]
) as dag:

    # Create tasks for each book
    for book in books:
        file_name = book["file_name"]
        title = book["title"]
        book_name = normalize_book_name(file_name)
        pdf_path = project_root / "docs" / file_name
        
        # Create extract task for this book
        extract_chunks_task = PythonOperator(
            task_id=f"extract_pdf_pages_{book_name}",
            python_callable=extract_pdf_chunks,
            op_kwargs={
                "pdf_path": str(pdf_path),
                "book_name": book_name,
                "output_dir": str(project_root / "temp_docs" / "chunks")
            }
        )
        
        # Create process task for this book
        process_chunks_task = PythonOperator(
            task_id=f"process_chunks_{book_name}",
            python_callable=process_chunks,
            op_kwargs={
                "input_dir": f"temp_docs/chunks",
                "book_name": title.lower()
            }
        )
        
        # Create mark_book_available task for this book
        mark_available_task = PythonOperator(
            task_id=f"mark_book_available_{book_name}",
            python_callable=mark_book_available,
            op_kwargs={
                "book_data": book
            }
        )
        
        # Set dependencies: process runs after extract, mark_available runs after process
        extract_chunks_task >> process_chunks_task >> mark_available_task

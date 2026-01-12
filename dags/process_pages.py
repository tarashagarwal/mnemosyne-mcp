import os
import re
import uuid
from dataclasses import dataclass
from typing import Iterable, List, Dict, Optional, Tuple
from datetime import datetime

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from dotenv import load_dotenv
from pathlib import Path


PAGE_RE = re.compile(r"page[_\- ](\d+)", re.IGNORECASE)


@dataclass
class IngestConfig:
    input_dir: str
    collection_name: str = "pages"
    batch_size: int = 64
    file_ext_allowlist: Tuple[str, ...] = (".md", ".txt")
    book_name: str = "future queen"


def extract_page_number(filename: str) -> Optional[int]:
    """
    Tries to extract page number from filename like:
    future_queen_page_003.md, book-page-12.txt, etc.
    """
    m = PAGE_RE.search(filename)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def normalize_text(text: str) -> str:
    # basic cleanup (keeps content but reduces noise)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def get_mongo_client() -> MongoClient:
    """
    Get MongoDB client using connection string from .env file.
    Expects MONGODB_CONNECTION_STRING in .env file.
    """
    # Load environment variables from .env file
    project_root = Path(__file__).resolve().parents[1]
    env_path = project_root / ".env"
    
    if env_path.exists():
        load_dotenv(env_path)
    else:
        # Try loading from current directory or parent
        load_dotenv()
    
    connection_string = os.getenv("MONGODB_CONNECTION_STRING")
    
    if not connection_string:
        raise ValueError(
            "MONGODB_CONNECTION_STRING not found in environment variables. "
            "Please add it to your .env file."
        )
    
    return MongoClient(connection_string)


def get_database_name() -> str:
    """
    Get MongoDB database name from .env file or use default.
    """
    project_root = Path(__file__).resolve().parents[1]
    env_path = project_root / ".env"
    
    if env_path.exists():
        load_dotenv(env_path)
    else:
        load_dotenv()
    
    # Default to 'mnemosyne' if not specified
    return os.getenv("MONGODB_DATABASE_NAME", "mnemosyne")


def iter_page_files(cfg: IngestConfig) -> Iterable[str]:
    """
    Recursively iterate through page files in the input directory and subdirectories.
    """
    input_path = Path(cfg.input_dir)
    for file_path in sorted(input_path.rglob("*")):
        if not file_path.is_file():
            continue
        if cfg.file_ext_allowlist and not file_path.suffix.lower() in cfg.file_ext_allowlist:
            continue
        yield str(file_path)


def build_document_for_file(
    file_path: str,
    cfg: IngestConfig,
) -> Optional[Dict]:
    """
    Build a MongoDB document for the whole page (not chunked).
    """
    filename = os.path.basename(file_path)
    page_number = extract_page_number(filename)

    # Read file and normalize text
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        page_text_raw = f.read()

    page_text = normalize_text(page_text_raw)
    if not page_text:
        return None

    # Create a MongoDB document for the whole page
    document: Dict = {
        "_id": str(uuid.uuid4()),
        "source_file": filename,
        "book_name": cfg.book_name.lower() if cfg.book_name else None,
        "page_number": page_number,
        "page_text": page_text,
        "is_whole_page": True,  # Flag to indicate this is a whole page, not a chunk
        "processed_date": datetime.now().isoformat(),
    }

    return document


def process_pages(input_dir: Optional[str] = None, book_name: Optional[str] = None) -> Dict[str, int]:
    """
    Main function to process whole pages (not chunks) and store in MongoDB.
    Returns stats useful for logs/XCom.
    """
    project_root = Path(__file__).resolve().parents[1]

    if input_dir is None:
        input_dir = project_root / "temp_docs" / "pages"
    else:
        input_dir = Path(input_dir)
        if not input_dir.is_absolute():
            input_dir = project_root / input_dir

    cfg = IngestConfig(
        input_dir=str(input_dir),
        collection_name="pages",
        batch_size=64,
        book_name=book_name,
    )

    if not os.path.isdir(cfg.input_dir):
        raise FileNotFoundError(f"Input dir not found: {cfg.input_dir}")

    # MongoDB client
    client = get_mongo_client()
    
    # Get database and collection
    db_name = get_database_name()
    db: Database = client[db_name]
    pages_collection: Collection = db[cfg.collection_name]

    total_files = 0
    total_pages_ingested = 0
    total_documents_inserted = 0

    buffer: List[Dict] = []

    for file_path in iter_page_files(cfg):
        total_files += 1
        document = build_document_for_file(file_path, cfg)
        if not document:
            continue

        total_pages_ingested += 1
        buffer.append(document)

        # flush in batches
        while len(buffer) >= cfg.batch_size:
            batch = buffer[: cfg.batch_size]
            buffer = buffer[cfg.batch_size :]
            pages_collection.insert_many(batch)
            total_documents_inserted += len(batch)

    # flush remaining
    if buffer:
        pages_collection.insert_many(buffer)
        total_documents_inserted += len(buffer)

    client.close()

    return {
        "files_seen": total_files,
        "pages_ingested": total_pages_ingested,
        "documents_inserted": total_documents_inserted,
        "collection": cfg.collection_name,
        "database": db_name,
    }


# Optional local run
if __name__ == "__main__":
    stats = process_pages(
        input_dir="/home/tarash-ubuntu/Personal/mnemosyne-mcp/temp_docs/pages",
        book_name="the_once_and_future_queen",
    )
    print(stats)


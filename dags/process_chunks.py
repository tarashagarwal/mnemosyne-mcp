
import os
import re
import uuid
import json
from dataclasses import dataclass
from typing import Iterable, List, Dict, Optional, Tuple

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer
from pathlib import Path


PAGE_RE = re.compile(r"page[_\- ](\d+)", re.IGNORECASE)


@dataclass
class IngestConfig:
    input_dir: str
    collection_name: str = "mnemosyne_pages"
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    chunk_words: int = 50
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


def chunk_by_words(text: str, words_per_chunk: int) -> List[str]:
    """
    Chunk into fixed-size 50-word chunks (approx paragraphs).
    Keeps original order. Does not overlap.
    """
    words = text.split()
    if not words:
        return []
    chunks = []
    for i in range(0, len(words), words_per_chunk):
        chunk = " ".join(words[i : i + words_per_chunk])
        chunks.append(chunk)
    return chunks


def get_chunks_dir(project_root: Path) -> Path:
    """Get the chunks directory path, creating it if needed."""
    chunks_dir = project_root / "temp_docs" / "chunk"
    chunks_dir.mkdir(parents=True, exist_ok=True)
    return chunks_dir


def get_chunks_file_path(chunks_dir: Path, source_filename: str) -> Path:
    """Get the path for storing chunks for a given source file."""
    # Replace extension with .json
    base_name = os.path.splitext(source_filename)[0]
    return chunks_dir / f"{base_name}_chunks.json"


def save_chunks(chunks_dir: Path, source_filename: str, chunks: List[str], page_text: str, page_number: Optional[int]) -> None:
    """Save chunks to disk as JSON."""
    chunks_file = get_chunks_file_path(chunks_dir, source_filename)
    data = {
        "source_file": source_filename,
        "page_number": page_number,
        "page_text": page_text,
        "chunks": chunks,
        "num_chunks": len(chunks),
    }
    with open(chunks_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_chunks(chunks_dir: Path, source_filename: str) -> Optional[Dict]:
    """Load chunks from disk if they exist."""
    chunks_file = get_chunks_file_path(chunks_dir, source_filename)
    if not chunks_file.exists():
        return None
    try:
        with open(chunks_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def ensure_collection(client: QdrantClient, collection: str, vector_size: int) -> None:
    """
    Create collection if missing. If it exists, we keep it.
    """
    existing = client.get_collections().collections
    names = {c.name for c in existing}
    if collection in names:
        return

    client.create_collection(
        collection_name=collection,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )


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


def build_points_for_file(
    file_path: str,
    model: SentenceTransformer,
    cfg: IngestConfig,
    chunks_dir: Path,
) -> List[PointStruct]:
    filename = os.path.basename(file_path)
    page_number = extract_page_number(filename)

    # Try to load chunks from disk first
    cached_data = load_chunks(chunks_dir, filename)
    
    if cached_data:
        # Use cached chunks
        page_text = cached_data.get("page_text", "")
        chunks = cached_data.get("chunks", [])
        print(f"  ✓ Loaded {len(chunks)} chunks from cache for {filename}")
    else:
        # Read file and create chunks
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            page_text_raw = f.read()

        page_text = normalize_text(page_text_raw)
        if not page_text:
            return []

        chunks = chunk_by_words(page_text, cfg.chunk_words)
        if not chunks:
            return []

        # Save chunks to disk for future use
        save_chunks(chunks_dir, filename, chunks, page_text, page_number)
        print(f"  ✓ Created and saved {len(chunks)} chunks for {filename}")

    # Embed chunks (not the whole page) - this is what you search against
    vectors = model.encode(chunks, normalize_embeddings=True)
    vectors = np.asarray(vectors, dtype=np.float32)

    points: List[PointStruct] = []
    for idx, chunk_text in enumerate(chunks):
        payload: Dict = {
            "source_file": filename,
            "book_name": cfg.book_name,       # hardcoded book name
            "page_number": page_number,       # can be None if not found
            "chunk_index": idx,               # 0-based chunk position in that page
            "page_text": page_text,           # whole page
            "chunk_text": chunk_text,         # 50-word chunk
            "chunk_words": cfg.chunk_words,
        }

        points.append(
            PointStruct(
                id=str(uuid.uuid4()),
                vector=vectors[idx].tolist(),
                payload=payload,
            )
        )

    return points


def process_chunks(input_dir: Optional[str] = None, book_name: Optional[str] = None) -> Dict[str, int]:
    """
    Main function you call from an Airflow task.
    Returns stats useful for logs/XCom.
    """
    project_root = Path(__file__).resolve().parents[1]

    if input_dir is None:
        input_dir = project_root / "temp_docs"
    else:
        input_dir = Path(input_dir)
        if not input_dir.is_absolute():
            input_dir = project_root / input_dir

    cfg = IngestConfig(
        input_dir=str(input_dir),
        collection_name="mnemosyne_pages",
        qdrant_host="localhost",
        qdrant_port=6333,
        chunk_words=50,
        batch_size=64,
        book_name=book_name,
    )

    if not os.path.isdir(cfg.input_dir):
        raise FileNotFoundError(f"Input dir not found: {cfg.input_dir}")

    # Get chunks directory
    chunks_dir = get_chunks_dir(project_root)

    # Qdrant client
    client = QdrantClient(host=cfg.qdrant_host, port=cfg.qdrant_port)

    # Embedding model
    model = SentenceTransformer(cfg.embedding_model)
    vector_size = model.get_sentence_embedding_dimension()

    # Ensure collection exists
    ensure_collection(client, cfg.collection_name, vector_size)

    total_files = 0
    total_pages_ingested = 0
    total_points = 0

    buffer: List[PointStruct] = []

    for file_path in iter_page_files(cfg):
        total_files += 1
        points = build_points_for_file(file_path, model, cfg, chunks_dir)
        if not points:
            continue

        total_pages_ingested += 1
        buffer.extend(points)

        # flush in batches
        while len(buffer) >= cfg.batch_size:
            batch = buffer[: cfg.batch_size]
            buffer = buffer[cfg.batch_size :]
            client.upsert(collection_name=cfg.collection_name, points=batch)
            total_points += len(batch)

    # flush remaining
    if buffer:
        client.upsert(collection_name=cfg.collection_name, points=buffer)
        total_points += len(buffer)

    return {
        "files_seen": total_files,
        "pages_ingested": total_pages_ingested,
        "points_upserted": total_points,
        "collection": cfg.collection_name,
    }


# Optional local run
if __name__ == "__main__":
    stats = process_chunks(
        input_dir="/home/tarash-ubuntu/Personal/mnemosyne-mcp/temp_docs/chunks",
        book_name="future_queen",
    )
    print(stats)

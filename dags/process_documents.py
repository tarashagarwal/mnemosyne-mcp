
import os
import re
import uuid
from dataclasses import dataclass
from typing import Iterable, List, Dict, Optional, Tuple

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer


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
    for name in sorted(os.listdir(cfg.input_dir)):
        path = os.path.join(cfg.input_dir, name)
        if not os.path.isfile(path):
            continue
        if cfg.file_ext_allowlist and not name.lower().endswith(cfg.file_ext_allowlist):
            continue
        yield path


def build_points_for_file(
    file_path: str,
    model: SentenceTransformer,
    cfg: IngestConfig,
) -> List[PointStruct]:
    filename = os.path.basename(file_path)
    page_number = extract_page_number(filename)

    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        page_text_raw = f.read()

    page_text = normalize_text(page_text_raw)
    if not page_text:
        return []

    chunks = chunk_by_words(page_text, cfg.chunk_words)
    if not chunks:
        return []

    # Embed chunks (not the whole page) - this is what you search against
    vectors = model.encode(chunks, normalize_embeddings=True)
    vectors = np.asarray(vectors, dtype=np.float32)

    points: List[PointStruct] = []
    for idx, chunk_text in enumerate(chunks):
        payload: Dict = {
            "source_file": filename,
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


def process_documents(cfg: IngestConfig) -> Dict[str, int]:
    """
    Main function you call from an Airflow task.
    Returns stats useful for logs/XCom.
    """
    if not os.path.isdir(cfg.input_dir):
        raise FileNotFoundError(f"Input dir not found: {cfg.input_dir}")

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
        points = build_points_for_file(file_path, model, cfg)
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
    cfg = IngestConfig(
        input_dir="/home/tarash-ubuntu/Personal/mnemosyne-mcp/temp_docs",
        collection_name="mnemosyne_pages",
        qdrant_host="localhost",
        qdrant_port=6333,
        embedding_model="sentence-transformers/all-MiniLM-L6-v2",
        chunk_words=50,
        batch_size=64,
    )
    stats = process_documents(cfg)
    print(stats)

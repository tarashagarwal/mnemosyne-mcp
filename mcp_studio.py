from mcp.server.fastmcp import FastMCP
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

mcp = FastMCP("Mnemosyne MCP")

client = QdrantClient("localhost", port=6333)
model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
COLLECTION = "mnemosyne_pages"


@mcp.tool()
def search_book(query: str, top_k: int = 10):
    """Find which page of a book called 'future queen' contains a given text or concept and return full page."""

    vector = model.encode(query).tolist()

    result = client.query_points(
        collection_name=COLLECTION,
        prefetch=[],
        query=vector,
        limit=top_k,
        with_payload=True,
    )

    hits = result.points

    MIN_SIMILARITY = 0.6
    SUBSTRING_BOOST = 0.20

    query_lower = query.lower()
    pages = {}

    for h in hits:
        p = h.payload
        chunk_text = p["chunk_text"]
        adjusted = h.score

        if query_lower in chunk_text.lower():
            adjusted = min(1.0, h.score + SUBSTRING_BOOST)

        if adjusted < MIN_SIMILARITY:
            continue

        page = p["page_number"]

        if page not in pages:
            pages[page] = {
                "page_number": page,
                "page_text": p["page_text"],
                "matches": [],
            }

        pages[page]["matches"].append({
            "chunk_text": chunk_text,
            "chunk_index": p["chunk_index"],
            "score": adjusted,
        })

    return list(pages.values())


if __name__ == "__main__":
    mcp.run()

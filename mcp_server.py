from fastapi import FastAPI
from pydantic import BaseModel
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

app = FastAPI()

client = QdrantClient("localhost", port=6333)
model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
COLLECTION = "mnemosyne_pages"


class SearchRequest(BaseModel):
    query: str
    top_k: int = 10


@app.post("/search")
def search(req: SearchRequest):
    query_vector = model.encode(req.query).tolist()

    result = client.query_points(
        collection_name=COLLECTION,
        prefetch=[],
        query=query_vector,
        limit=req.top_k,
        with_payload=True,
    )

    hits = result.points

    # Filter matches with similarity >= 90% (0.9)
    MIN_SIMILARITY = 0.8
    SUBSTRING_BOOST = 0.20

    # Apply substring boost and filter
    query_lower = req.query.lower()
    filtered_hits = []
    for h in hits:
        chunk_text_lower = h.payload["chunk_text"].lower()
        adjusted_score = h.score
        
        # If query is a substring of chunk text, add boost
        if query_lower in chunk_text_lower:
            adjusted_score = min(1.0, h.score + SUBSTRING_BOOST)
        
        # Filter by adjusted score
        if adjusted_score >= MIN_SIMILARITY:
            # Update the score in the hit object
            h.score = adjusted_score
            filtered_hits.append(h)

    # group by page
    pages = {}

    for h in filtered_hits:
        p = h.payload
        page = p["page_number"]

        if page not in pages:
            pages[page] = {
                "page_number": page,
                "page_text": p["page_text"],
                "matches": [],
            }

        pages[page]["matches"].append({
            "chunk_text": p["chunk_text"],
            "chunk_index": p["chunk_index"],
            "score": h.score,
        })

    return {
        "query": req.query,
        "pages": list(pages.values()),
    }


if __name__ == "__main__":
    import uvicorn
    
    print("Starting MCP Server...")
    print("Server will be available at http://localhost:8000")
    print("API docs available at http://localhost:8000/docs")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)

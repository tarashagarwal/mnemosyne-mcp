from fastapi import FastAPI
from pydantic import BaseModel
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

app = FastAPI()

client = QdrantClient("localhost", port=6333)
model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
COLLECTION = "mnemosyne_pages"

class QueryRequest(BaseModel):
    query: str
    top_k: int = 10


@app.post("/query")
def query_pages(req: QueryRequest):
    vector = model.encode(req.query).tolist()

    results = client.search(
        collection_name=COLLECTION,
        query_vector=vector,
        limit=req.top_k,
    )

    # Deduplicate by page
    pages = {}
    for r in results:
        payload = r.payload
        page = payload["page_number"]

        if page not in pages:
            pages[page] = {
                "page_number": page,
                "source_file": payload["source_file"],
                "page_text": payload["page_text"],
            }

    return {
        "query": req.query,
        "pages": list(pages.values())
    }


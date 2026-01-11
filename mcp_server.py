import os
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
from pymongo import MongoClient
from dotenv import load_dotenv

app = FastAPI()

client = QdrantClient("localhost", port=6333)
model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
COLLECTION = "mnemosyne_pages"

# MongoDB connection helpers
def get_mongo_client() -> MongoClient:
    """Get MongoDB client using connection string from .env file."""
    project_root = Path(__file__).resolve().parents[0]
    env_path = project_root / ".env"
    
    if env_path.exists():
        load_dotenv(env_path)
    else:
        load_dotenv()
    
    connection_string = os.getenv("MONGODB_CONNECTION_STRING")
    
    if not connection_string:
        raise ValueError(
            "MONGODB_CONNECTION_STRING not found in environment variables. "
            "Please add it to your .env file."
        )
    
    return MongoClient(connection_string)


def get_database_name() -> str:
    """Get MongoDB database name from .env file or use default."""
    project_root = Path(__file__).resolve().parents[0]
    env_path = project_root / ".env"
    
    if env_path.exists():
        load_dotenv(env_path)
    else:
        load_dotenv()
    
    return os.getenv("MONGODB_DATABASE_NAME", "mnemosyne")


class SearchRequest(BaseModel):
    query: str
    top_k: int = 10


class BookAvailabilityRequest(BaseModel):
    title: Optional[str] = None
    author: Optional[str] = None
    isbn: Optional[str] = None


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


@app.post("/check_book_availability")
def check_book_availability(req: BookAvailabilityRequest):
    """
    Check if a book is available in MongoDB.
    Can search by title, author, ISBN, or any combination.
    Returns book information if found and available.
    """
    try:
        # Validate that at least one search parameter is provided
        if not req.title and not req.author and not req.isbn:
            raise HTTPException(
                status_code=400,
                detail="At least one of 'title', 'author', or 'isbn' must be provided"
            )
        
        # Get MongoDB client
        mongo_client = get_mongo_client()
        db_name = get_database_name()
        db = mongo_client[db_name]
        books_collection = db["books"]
        
        # Build query - search fields are stored in lowercase
        query = {}
        if req.title:
            query["title"] = req.title.lower()
        if req.author:
            query["author"] = req.author.lower()
        if req.isbn:
            query["isbn"] = req.isbn.lower()
        
        # Search for the book
        book = books_collection.find_one(query)
        
        mongo_client.close()
        
        if not book:
            return {
                "available": False,
                "message": "Book not found in database",
                "book": None
            }
        
        # Check if book status is "available"
        status = book.get("status", "").lower()
        is_available = status == "available"
        
        # Prepare book info (remove MongoDB _id, convert to string if needed)
        book_info = {
            "title": book.get("title"),
            "author": book.get("author"),
            "isbn": book.get("isbn"),
            "publisher": book.get("publisher"),
            "publication_date": book.get("publication_date"),
            "pages": book.get("pages"),
            "language": book.get("language"),
            "description": book.get("description"),
            "tags": book.get("tags", []),
            "status": book.get("status"),
            "file_name": book.get("file_name"),
            "added_date": book.get("added_date"),
            "processed_date": book.get("processed_date"),
        }
        
        return {
            "available": is_available,
            "message": f"Book found with status: {status}",
            "book": book_info
        }
        
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error checking book availability: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    
    print("Starting MCP Server...")
    print("Server will be available at http://localhost:8000")
    print("API docs available at http://localhost:8000/docs")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)

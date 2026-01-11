import os
from pathlib import Path
from typing import Optional
from mcp.server.fastmcp import FastMCP
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
from pymongo import MongoClient
from dotenv import load_dotenv

mcp = FastMCP("Mnemosyne MCP")

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


@mcp.tool()
def check_book_availability(
    title: Optional[str] = None,
    author: Optional[str] = None,
    isbn: Optional[str] = None
):
    """
    Check if a book is available in Books Database by searching with title, author, or ISBN.
    At least one parameter (title, author, or isbn) must be provided.
    Returns book information and availability status.
    """
    # Validate that at least one search parameter is provided
    if not title and not author and not isbn:
        return {
            "available": False,
            "message": "At least one of 'title', 'author', or 'isbn' must be provided",
            "book": None
        }
    
    try:
        # Get MongoDB client
        mongo_client = get_mongo_client()
        db_name = get_database_name()
        db = mongo_client[db_name]
        books_collection = db["books"]
        
        # Build query - search fields are stored in lowercase
        query = {}
        if title:
            query["title"] = title.lower()
        if author:
            query["author"] = author.lower()
        if isbn:
            query["isbn"] = isbn.lower()
        
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
        
    except ValueError as e:
        return {
            "available": False,
            "message": str(e),
            "book": None
        }
    except Exception as e:
        return {
            "available": False,
            "message": f"Error checking book availability: {str(e)}",
            "book": None
        }


if __name__ == "__main__":
    mcp.run()

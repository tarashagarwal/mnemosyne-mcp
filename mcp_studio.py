import os
from pathlib import Path
from typing import Optional, Dict
from datetime import datetime
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


def get_last_page(book_name: str) -> Optional[int]:
    """
    Get the last accessed page number for a book from MongoDB.
    """
    try:
        mongo_client = get_mongo_client()
        db_name = get_database_name()
        db = mongo_client[db_name]
        last_page_collection = db["last_page"]
        
        # Search for last page record (book_name is stored in lowercase)
        record = last_page_collection.find_one({"book_name": book_name.lower()})
        
        mongo_client.close()
        
        if record:
            return record.get("page_number")
        return None
    except Exception as e:
        print(f"Error getting last page: {str(e)}")
        return None


def update_last_page(book_name: str, page_number: int) -> bool:
    """
    Update the last accessed page number for a book in MongoDB.
    """
    try:
        mongo_client = get_mongo_client()
        db_name = get_database_name()
        db = mongo_client[db_name]
        last_page_collection = db["last_page"]
        
        # Upsert the last page record
        last_page_collection.update_one(
            {"book_name": book_name.lower()},
            {
                "$set": {
                    "book_name": book_name.lower(),
                    "page_number": page_number,
                    "updated_at": datetime.now().isoformat()
                }
            },
            upsert=True
        )
        
        mongo_client.close()
        return True
    except Exception as e:
        print(f"Error updating last page: {str(e)}")
        return False


def get_page_from_db(book_name: str, page_number: int) -> Optional[Dict]:
    """
    Get a specific page from MongoDB pages collection.
    """
    try:
        mongo_client = get_mongo_client()
        db_name = get_database_name()
        db = mongo_client[db_name]
        pages_collection = db["pages"]
        
        # Search for the page (book_name and page_number are stored in lowercase/number)
        page = pages_collection.find_one({
            "book_name": book_name.lower(),
            "page_number": page_number
        })
        
        mongo_client.close()
        
        if page:
            # Remove MongoDB _id and return page data
            page_data = {
                "book_name": page.get("book_name"),
                "page_number": page.get("page_number"),
                "page_text": page.get("page_text"),
                "source_file": page.get("source_file"),
            }
            return page_data
        return None
    except Exception as e:
        print(f"Error getting page from database: {str(e)}")
        return None


@mcp.tool()
def get_page(book_name: str, page_number: Optional[int] = None) -> Dict:
    """
    Get a page from a book by name and page number.
    If page_number is not provided, starts from the last accessed page.
    Stores the accessed page number in MongoDB 'last_page' collection.
    
    Args:
        book_name: Name of the book (case-insensitive)
        page_number: Optional page number. If not provided, uses last accessed page or starts from page 1.
    
    Returns:
        Dictionary with page information including page_text, page_number, book_name, and message.
    """
    try:
        # If page_number not provided, get from last_page collection or default to 1
        if page_number is None:
            last_page = get_last_page(book_name)
            page_number = last_page if last_page is not None else 1
        
        # Get the page from MongoDB
        page_data = get_page_from_db(book_name, page_number)
        
        if not page_data:
            return {
                "success": False,
                "message": f"Page {page_number} not found for book '{book_name}'",
                "book_name": book_name.lower(),
                "page_number": page_number,
                "page_text": None
            }
        
        # Update last page in MongoDB
        update_last_page(book_name, page_number)
        
        return {
            "success": True,
            "message": f"Retrieved page {page_number} from '{book_name}'",
            "book_name": page_data["book_name"],
            "page_number": page_data["page_number"],
            "page_text": page_data["page_text"],
            "source_file": page_data.get("source_file")
        }
        
    except Exception as e:
        return {
            "success": False,
            "message": f"Error retrieving page: {str(e)}",
            "book_name": book_name.lower() if book_name else None,
            "page_number": page_number,
            "page_text": None
        }


@mcp.tool()
def get_next_page(book_name: str) -> Dict:
    """
    Get the next page for a book and update the last page tracker.
    Increments the current last page by 1 and retrieves that page.
    
    Args:
        book_name: Name of the book (case-insensitive)
    
    Returns:
        Dictionary with next page information including page_text, page_number, book_name, and message.
    """
    try:
        # Get current last page
        last_page = get_last_page(book_name)
        
        # If no last page exists, start from page 1
        if last_page is None:
            next_page_number = 1
        else:
            next_page_number = last_page + 1
        
        # Get the next page
        page_data = get_page_from_db(book_name, next_page_number)
        
        if not page_data:
            return {
                "success": False,
                "message": f"Next page ({next_page_number}) not found for book '{book_name}'. You may have reached the end of the book.",
                "book_name": book_name.lower(),
                "page_number": next_page_number,
                "page_text": None,
                "is_end_of_book": True
            }
        
        # Update last page to the next page
        update_last_page(book_name, next_page_number)
        
        return {
            "success": True,
            "message": f"Retrieved next page ({next_page_number}) from '{book_name}'",
            "book_name": page_data["book_name"],
            "page_number": page_data["page_number"],
            "page_text": page_data["page_text"],
            "source_file": page_data.get("source_file"),
            "is_end_of_book": False
        }
        
    except Exception as e:
        return {
            "success": False,
            "message": f"Error retrieving next page: {str(e)}",
            "book_name": book_name.lower() if book_name else None,
            "page_number": None,
            "page_text": None
        }


if __name__ == "__main__":
    mcp.run()

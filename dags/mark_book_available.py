import os
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database


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


def to_lowercase(value):
    """
    Convert value to lowercase if it's a string, otherwise return as-is.
    Returns None if value is None.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value.lower()
    return value


def mark_book_available(book_data: Dict) -> Dict[str, any]:
    """
    Mark a book as available in MongoDB by inserting/updating book information.
    
    Args:
        book_data: Dictionary containing book information with keys:
            - title: Book title
            - file_name: PDF file name
            - author: Author name
            - publisher: Publisher name
            - publication_date: Publication date (YYYY-MM-DD)
            - isbn: ISBN number
            - pages: Number of pages
            - language: Language
            - description: Book description
            - tags: List of tags
            - status: Book status (will be updated to "available")
            - added_date: Date when book was added
    
    Returns:
        Dictionary with operation result including:
            - success: Boolean indicating success
            - book_id: MongoDB document ID
            - message: Status message
    """
    try:
        # Get MongoDB client
        client = get_mongo_client()
        
        # Get database and collection
        db_name = get_database_name()
        db: Database = client[db_name]
        books_collection: Collection = db["books"]
        
        # Prepare book document with all string fields converted to lowercase
        book_doc = {
            "title": to_lowercase(book_data.get("title")),
            "file_name": to_lowercase(book_data.get("file_name")),
            "author": to_lowercase(book_data.get("author")),
            "publisher": to_lowercase(book_data.get("publisher")),
            "publication_date": to_lowercase(book_data.get("publication_date")),
            "isbn": to_lowercase(book_data.get("isbn")),
            "pages": book_data.get("pages"),  # Keep as integer
            "language": to_lowercase(book_data.get("language")),
            "description": to_lowercase(book_data.get("description")),
            "tags": [to_lowercase(tag) for tag in book_data.get("tags", []) if tag is not None] if book_data.get("tags") else [],
            "status": "available",  # Mark as available after processing (already lowercase)
            "added_date": to_lowercase(book_data.get("added_date")),
            "processed_date": datetime.now().isoformat().lower(),  # Add processing timestamp
        }
        
        # Use ISBN or title+author as unique identifier for upsert (already lowercase)
        filter_query = {}
        if book_doc.get("isbn"):
            filter_query["isbn"] = book_doc["isbn"]
        else:
            # Fallback to title + author if no ISBN
            filter_query = {
                "title": book_doc["title"],
                "author": book_doc["author"]
            }
        
        # Upsert (update if exists, insert if not)
        result = books_collection.update_one(
            filter_query,
            {"$set": book_doc},
            upsert=True
        )
        
        # Get the document ID
        if result.upserted_id:
            book_id = result.upserted_id
        else:
            # Document was updated, find it to get the ID
            book = books_collection.find_one(filter_query)
            book_id = book["_id"] if book else None
        
        client.close()
        
        return {
            "success": True,
            "book_id": str(book_id),
            "message": f"Book '{book_doc['title']}' marked as available in MongoDB",
            "upserted": result.upserted_id is not None,
            "modified": result.modified_count > 0
        }
        
    except Exception as e:
        return {
            "success": False,
            "book_id": None,
            "message": f"Error marking book as available: {str(e)}",
            "error": str(e)
        }


# For testing purposes
if __name__ == "__main__":
    # Example usage
    test_book = {
        "title": "The Once and Future Queen",
        "file_name": "the_once_and_future_queen.pdf",
        "author": "Paula Lafferty",
        "publisher": "Kensington Publishing Corp",
        "publication_date": "2024-01-01",
        "isbn": "978-0-06-327399-3",
        "pages": 504,
        "language": "English",
        "description": "A fantasy novel about a queen who is reborn and must reclaim her throne.",
        "tags": ["fantasy", "fiction", "queen", "rebellion"],
        "status": "to_read",
        "added_date": "2025-01-27"
    }
    
    result = mark_book_available(test_book)
    print(result)


from pathlib import Path
from typing import Optional
import tempfile

from docling.document_converter import DocumentConverter
from pypdf import PdfReader, PdfWriter


def extract_pdf_pages(
    pdf_path: str,
    book_name: str,
    output_dir: Optional[str] = None,
) -> str:
    """
    Extracts pages from a PDF using Docling and saves each page as a Markdown file.
    """

    pdf_path = Path(pdf_path).resolve()

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    project_root = Path(__file__).resolve().parents[1]

    if output_dir is None:
        output_dir = project_root / "temp_docs"
    else:
        output_dir = Path(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    print("--------------------------------------------------")
    print(f"Extracting pages from: {pdf_path}")
    print(f"Book name: {book_name}")
    print(f"Output directory: {output_dir}")
    print(f"Project root: {project_root}")
    print("--------------------------------------------------")

    converter = DocumentConverter()
    
    # Read PDF to get page count and extract individual pages
    reader = PdfReader(str(pdf_path))
    total_pages = len(reader.pages)
    
    print(f"Processing {total_pages} pages...")
    
    # Process each page separately
    for page_num in range(total_pages):
        # Create a temporary single-page PDF for this page
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_pdf:
            writer = PdfWriter()
            writer.add_page(reader.pages[page_num])
            writer.write(tmp_pdf)
            tmp_pdf_path = tmp_pdf.name
        
        try:
            # Convert the single page with Docling
            doc = converter.convert(tmp_pdf_path)
            page_md = doc.document.export_to_markdown()
            
            # Save the markdown
            page_file = output_dir / f"{book_name}_page_{page_num + 1:03d}.md"
            page_file.write_text(page_md, encoding="utf-8")
            
            print(f"  ✓ Page {page_num + 1}/{total_pages}")
        finally:
            # Clean up temporary file
            Path(tmp_pdf_path).unlink()

    print(f"✅ Extracted {total_pages} pages")

    return str(output_dir)


# ---------------------------
# Main (arguments defined here)
# ---------------------------
def main():
    project_root = Path(__file__).resolve().parents[1]

    pdf_path = project_root / "docs/future_queen.pdf"
    print(pdf_path)
    book_name = "future_queen"
    output_dir = project_root / "temp_docs"

    extract_pdf_pages(
        pdf_path=str(pdf_path),
        book_name=book_name,
        output_dir=str(output_dir),
    )


if __name__ == "__main__":
    main()

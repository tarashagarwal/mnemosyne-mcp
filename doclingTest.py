from docling.document_converter import DocumentConverter

converter = DocumentConverter()
doc = converter.convert("./docs/future_queen.pdf")

print(doc.document.export_to_markdown())
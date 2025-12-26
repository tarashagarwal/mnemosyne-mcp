from docling.document_converter import DocumentConverter

converter = DocumentConverter()
doc = converter.convert("./docs/example.pdf")

print(doc.document.export_to_markdown())
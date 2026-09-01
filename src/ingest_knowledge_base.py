"""
One-time (or re-run-when-content-changes) ingestion script.
Reads each .txt article in data/support_kb/, embeds it as a single chunk
(no splitting — articles are short enough), and stores it in a dedicated
ChromaDB collection called "support_kb", at a persist_dir belonging
entirely to support-triage.
"""

import sys
from pathlib import Path
import chromadb
import os

from dotenv import load_dotenv
load_dotenv()

DOCUMENT_QA_APP_SRC = os.environ.get("DOCUMENT_QA_APP_SRC")
if DOCUMENT_QA_APP_SRC is None:
    raise ValueError(f"Document QA application path not found")

if DOCUMENT_QA_APP_SRC:
    sys.path.append(DOCUMENT_QA_APP_SRC)

from src.embedding import embed_chunks , load_model
model = load_model()

SUPPORT_KB_DIR = Path("data/support_kb")
PERSIST_DIR = "data/chroma_db"          
COLLECTION_NAME = "support_kb"


def load_articles(directory: Path) -> list[dict]:
    """
    TODO: read every .txt file in `directory`.
    Return a list of dicts, one per file, e.g.:
        {"id": "billing_duplicate_charge", "text": "<full file contents>"}
    Decide: what's the id — filename without extension? Something else?
    """
    file_dic = []
    for file_path in directory.glob("*.txt"):
        try:
            content = file_path.read_text(encoding="utf-8")
            file_dic.append({"id": file_path.stem, "chunk_text": content,
                            "metadata": {"page_num": 0,"source": file_path.name,"is_table": False}})
        except Exception as e:
            print(f"Error reading {file_path.name}: {e}")
            
    return file_dic

def main():
    articles = load_articles(SUPPORT_KB_DIR)
    if len(articles) < 1:
        print("No articles found, aborting.")
        sys.exit(1)
    embedded_chunks = embed_chunks(articles, model)
    client = chromadb.PersistentClient(path=PERSIST_DIR)
    collection = client.get_or_create_collection(COLLECTION_NAME)
    for chunk in embedded_chunks:
        collection.add(
                    ids=[chunk["id"]],
                    embeddings=[chunk["embedding"]],
                    documents=[chunk["chunk_text"]],
                    metadatas=[chunk["metadata"]],
)
    print(f"Ingested {len(articles)} articles into '{COLLECTION_NAME}' at {PERSIST_DIR}")


if __name__ == "__main__":
    main()
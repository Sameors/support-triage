import chromadb
from sentence_transformers import SentenceTransformer


def query_chunks(query: str, model, client: chromadb.PersistentClient,
                  collection_name: str, n_results: int = 5) -> list[dict]:
    """
    Given a user's question and a document's collection name, return
    the top-k most relevant chunks from that document's collection.
    """
    
    query_embedding = embed_query(query, model)
    #query_name = get_collection_name(source)
    collection = client.get_collection(name = collection_name)
    results = collection.query(
        query_embeddings= [query_embedding],
        n_results= n_results,
        )
    matched_chunks = []
    for chunk_id, chunk_text, metadata, distance in zip(
            results['ids'][0], results['documents'][0], results['metadatas'][0], results['distances'][0]):
        matched_chunks.append({
            'chunk_id': chunk_id,
            'chunk_text': chunk_text,
            'page_num': metadata['page_num'],
            'source': metadata['source'],
            'is_table': metadata['is_table'],
            'distance': distance,
            })
    #print(matched_chunks)
    return matched_chunks


def embed_query(query: str, model: SentenceTransformer):
    
    """
    Embed a single user query string — called at RETRIEVAL time, not
    indexing time. Lives here (not in retrieval.py) because it's still
    fundamentally "text -> vector via this model" 
    """
    query_length= len(model.tokenizer(query)["input_ids"])
    if (query_length) > model.max_seq_length:
        print(f"chunk_length({query_length}) is greater than allowed size {model.max_seq_length}")
    query_embeddings = model.encode(query, normalize_embeddings=True)
    return query_embeddings

def load_model(model_name: str = "all-MiniLM-L6-v2") -> SentenceTransformer:
    
    """Load and return a SentenceTransformer model.
        """
        
    model = SentenceTransformer(model_name)
    return model
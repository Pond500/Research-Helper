import os
from typing import List, Optional
from langchain_core.documents import Document
from .state import Resource

COLLECTION_NAME = "research_docs"

_client = None
_vector_store = None
_embeddings = None
_qdrant_available = None  # None = untested, True/False = known


def _init_qdrant() -> bool:
    """Try to initialise Qdrant lazily. Returns True if available."""
    global _client, _vector_store, _embeddings, _qdrant_available
    if _qdrant_available is not None:
        return _qdrant_available
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams
        from langchain_qdrant import QdrantVectorStore
        from langchain_huggingface import HuggingFaceEmbeddings

        _client = QdrantClient(url=os.getenv("QDRANT_URL", "http://localhost:10237"), timeout=3)
        _embeddings = HuggingFaceEmbeddings(model_name="BAAI/bge-m3")

        try:
            _client.get_collection(collection_name=COLLECTION_NAME)
        except Exception:
            _client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(size=1024, distance=Distance.COSINE),
            )

        _vector_store = QdrantVectorStore(
            client=_client,
            collection_name=COLLECTION_NAME,
            embedding=_embeddings,
        )
        _qdrant_available = True
    except Exception as e:
        print(f"[qdrant] Not available (Docker likely not running): {e}")
        _qdrant_available = False
    return _qdrant_available


SIMILARITY_THRESHOLD = 0.4  # drop chunks below this cosine score

async def search_qdrant(query: str, max_results: int = 10) -> List[Resource]:
    """Search local Qdrant vector database for uploaded context."""
    if not _init_qdrant():
        return []
    resources: List[Resource] = []
    try:
        # Fetch 3× more candidates then filter by similarity score
        candidates = await _vector_store.asimilarity_search_with_score(
            query, k=max_results * 3
        )
        results = [
            (doc, score) for doc, score in candidates if score >= SIMILARITY_THRESHOLD
        ][:max_results]

        for i, (doc, score) in enumerate(results):
            source = doc.metadata.get("source", f"Uploaded Document {i}")
            resources.append({
                "url": f"file://{source}",
                "title": f"[Qdrant DB] {source}",
                "description": doc.page_content,
                "resource_type": "web",
                "source": "qdrant",
            })
    except Exception as e:
        print(f"[qdrant] Search error for '{query}': {e}")
    return resources


def add_documents_to_qdrant(documents: List[Document]):
    """Add document chunks to Qdrant (raises if Qdrant is unavailable)."""
    if not _init_qdrant():
        raise RuntimeError("Qdrant is not available. Start Docker: docker-compose up -d")
    _vector_store.add_documents(documents)

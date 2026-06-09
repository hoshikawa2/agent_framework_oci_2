from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from .vector_store import VectorDocument, create_vector_store
from .graph_store import create_graph_store

@dataclass
class RagResult:
    query: str
    documents: list[VectorDocument]
    graph_neighbors: list[Any]
    latency_ms: int
    metadata: dict[str, Any]

    def as_prompt_context(self, max_chars: int = 6000) -> str:
        chunks=[]; total=0
        for i, doc in enumerate(self.documents, start=1):
            text=(doc.content or '').strip()
            if not text: continue
            piece=f"[doc:{i} score={doc.score:.4f} id={doc.id}]\n{text}\n"
            if total + len(piece) > max_chars: break
            chunks.append(piece); total += len(piece)
        return "\n".join(chunks)

class RagService:
    """RAG operacional: vector search + grafo + telemetria FIRST-like."""
    def __init__(self, settings, embedding_provider=None, telemetry=None):
        self.settings=settings
        self.telemetry=telemetry
        self.vector_store=create_vector_store(settings, embedding_provider=embedding_provider, telemetry=telemetry)
        self.graph_store=create_graph_store(settings, telemetry=telemetry)

    async def add_documents(self, texts: list[str], metadatas: list[dict] | None = None, namespace: str='default') -> list[str]:
        start=time.time()
        ids=await self.vector_store.add_texts(texts, metadatas=metadatas, namespace=namespace)
        if self.telemetry:
            await self.telemetry.rag_event('documents.added', namespace, len(ids), {
                'namespace': namespace, 'document_count': len(ids), 'latency_ms': int((time.time()-start)*1000)
            })
        return ids

    async def retrieve(self, query: str, *, namespace: str='default', k: int | None=None, graph_node: str | None=None) -> RagResult:
        start=time.time(); k=k or self.settings.RAG_TOP_K
        docs=await self.vector_store.similarity_search(query, k=k, namespace=namespace)
        neighbors=[]
        if graph_node:
            neighbors=await self.graph_store.neighbors(graph_node)
        result=RagResult(query=query, documents=docs, graph_neighbors=neighbors, latency_ms=int((time.time()-start)*1000), metadata={'namespace':namespace,'k':k})
        if self.telemetry:
            await self.telemetry.rag_event('retrieve.completed', query, len(docs), {
                'namespace': namespace, 'k': k, 'latency_ms': result.latency_ms, 'graph_neighbors': len(neighbors),
                'top_scores': [round(d.score, 6) for d in docs[:5]],
            })
        return result

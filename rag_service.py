#!/usr/bin/env python3
"""
RAG Ingestion Service with document chunking, metadata tagging, 
Nomic Embed v1.5 integration, and Qdrant storage.
"""

import os
import uuid
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime

import httpx
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
    MatchAny,
)

logger = logging.getLogger(__name__)
DEFAULT_WORKSPACE_ID = os.getenv("RAG_DEFAULT_WORKSPACE_ID", "default").strip() or "default"


class DocumentChunker:
    """Handles document chunking with configurable size and overlap."""
    
    def __init__(self, chunk_size: int = 1000, overlap: int = 100):
        self.chunk_size = chunk_size
        self.overlap = overlap
    
    def chunk_text(self, text: str, metadata: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Split text into overlapping chunks.
        
        Args:
            text: Text to chunk
            metadata: Optional metadata to attach to each chunk
            
        Returns:
            List of chunk dictionaries with text and metadata
        """
        if not text:
            return []
        
        chunks = []
        start = 0
        chunk_index = 0
        
        while start < len(text):
            end = start + self.chunk_size
            chunk_text = text[start:end]
            
            chunk_metadata = metadata.copy() if metadata else {}
            chunk_metadata.update({
                "chunk_index": chunk_index,
                "chunk_start": start,
                "chunk_end": min(end, len(text)),
                "total_length": len(text)
            })
            
            chunks.append({
                "text": chunk_text,
                "metadata": chunk_metadata
            })
            
            start += (self.chunk_size - self.overlap)
            chunk_index += 1
        
        return chunks


class NomicEmbedder:
    """Handles embeddings using Nomic Embed v1.5 model."""
    
    def __init__(self, model_name: str = "nomic-ai/nomic-embed-text-v1.5"):
        logger.info(f"Loading embedding model: {model_name}")
        self.model = SentenceTransformer(
            model_name,
            trust_remote_code=True
        )
        self.dimension = self.model.get_sentence_embedding_dimension()
        logger.info(f"Embedding model loaded. Dimension: {self.dimension}")
    
    def embed_text(self, text: str) -> List[float]:
        """Generate embedding for a single text."""
        embedding = self.model.encode(text, convert_to_numpy=True)
        return embedding.tolist()
    
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a batch of texts."""
        embeddings = self.model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        return embeddings.tolist()


class HTTPEmbeddingServiceClient:
    """Embedding client that delegates vectorization to a local HTTP service."""

    def __init__(
        self,
        service_url: str,
        model_name: str = "nomic-ai/nomic-embed-text-v1.5",
        timeout_seconds: float = 60.0,
    ):
        self.service_url = service_url.rstrip("/")
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        self.dimension = self._fetch_dimension()
        logger.info(
            "Connected to embedding service at %s with model %s (dimension=%s)",
            self.service_url,
            self.model_name,
            self.dimension,
        )

    def _fetch_dimension(self) -> int:
        """Fetch embedding dimension from the service health endpoint."""
        try:
            response = httpx.get(
                f"{self.service_url}/health",
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            dimension = payload.get("dimension")
            if not isinstance(dimension, int) or dimension <= 0:
                raise ValueError("Embedding service returned invalid dimension")
            return dimension
        except Exception as exc:
            logger.error("Failed to fetch embedding dimension from %s: %s", self.service_url, exc)
            raise

    def embed_text(self, text: str) -> List[float]:
        """Generate embedding for a single text via HTTP service."""
        embeddings = self.embed_batch([text])
        return embeddings[0]

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a batch of texts via HTTP service."""
        if not texts:
            return []

        response = httpx.post(
            f"{self.service_url}/v1/embeddings",
            json={
                "model": self.model_name,
                "input": texts,
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data", [])
        return [item["embedding"] for item in data]


class QdrantStorage:
    """Handles storage and retrieval from Qdrant vector database."""
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 6333,
        collection_name: str = "documents"
    ):
        self.client = QdrantClient(host=host, port=port)
        self.collection_name = collection_name
        logger.info(f"Connected to Qdrant at {host}:{port}")

    @staticmethod
    def _normalize_workspace_id(workspace_id: Any) -> str:
        """Normalize and validate workspace IDs used for isolation."""
        normalized = str(workspace_id).strip() if workspace_id is not None else ""
        if not normalized:
            raise ValueError("workspace_id must be a non-empty string")
        return normalized

    @staticmethod
    def _extract_workspace_id_from_filter_value(filter_value: Any) -> str:
        """
        Resolve workspace_id from filter value.

        Accepts either:
        - scalar: "acme"
        - any-clause: {"any": ["acme"]} (single unique value only)
        """
        if isinstance(filter_value, dict):
            if "any" not in filter_value:
                raise ValueError(
                    "workspace_id filter must be a scalar or {'any': [...]} clause"
                )

            any_values = filter_value.get("any")
            if not isinstance(any_values, list) or not any_values:
                raise ValueError("workspace_id any filter must contain at least one value")

            normalized_values = {
                QdrantStorage._normalize_workspace_id(value) for value in any_values
            }
            if len(normalized_values) != 1:
                raise ValueError(
                    "workspace_id any filter must contain a single unique workspace_id"
                )
            return next(iter(normalized_values))

        return QdrantStorage._normalize_workspace_id(filter_value)
    
    def create_collection(self, vector_size: int):
        """Create a new collection if it doesn't exist."""
        try:
            collections = self.client.get_collections().collections
            collection_names = [col.name for col in collections]
            
            if self.collection_name in collection_names:
                logger.info(f"Collection '{self.collection_name}' already exists")
                return
            
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=vector_size,
                    distance=Distance.COSINE
                )
            )
            logger.info(f"Created collection '{self.collection_name}'")
        except Exception as e:
            logger.error(f"Error creating collection: {e}")
            raise
    
    def upsert_points(
        self,
        texts: List[str],
        embeddings: List[List[float]],
        metadatas: List[Dict[str, Any]],
        workspace_id: str,
    ) -> List[str]:
        """
        Insert or update points in the collection.
        
        Args:
            texts: List of text chunks
            embeddings: List of embedding vectors
            metadatas: List of metadata dictionaries
            
        Returns:
            List of point IDs
        """
        normalized_workspace_id = self._normalize_workspace_id(workspace_id)
        points = []
        point_ids = []
        
        for text, embedding, metadata in zip(texts, embeddings, metadatas):
            point_id = str(uuid.uuid4())
            point_ids.append(point_id)

            metadata_payload = metadata.copy() if metadata else {}
            metadata_workspace_id = metadata_payload.get("workspace_id")
            if metadata_workspace_id is not None:
                normalized_metadata_workspace = self._normalize_workspace_id(metadata_workspace_id)
                if normalized_metadata_workspace != normalized_workspace_id:
                    raise ValueError(
                        "metadata.workspace_id must match the workspace_id argument"
                    )
            metadata_payload["workspace_id"] = normalized_workspace_id
            
            payload = {
                "text": text,
                "workspace_id": normalized_workspace_id,
                "metadata": metadata_payload,
                "ingested_at": datetime.utcnow().isoformat()
            }
            
            points.append(
                PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload=payload
                )
            )
        
        self.client.upsert(
            collection_name=self.collection_name,
            points=points
        )
        
        logger.info(f"Upserted {len(points)} points to collection '{self.collection_name}'")
        return point_ids
    
    def search(
        self,
        query_vector: List[float],
        workspace_id: str,
        limit: int = 10,
        filter_conditions: Optional[Dict[str, Any]] = None,
        collection_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search for similar documents.
        
        Args:
            query_vector: Query embedding vector
            limit: Maximum number of results
            filter_conditions: Optional metadata filters
            collection_name: Optional collection name override
            
        Returns:
            List of search results with text, metadata, and score
        """
        normalized_workspace_id = self._normalize_workspace_id(workspace_id)
        conditions = [
            FieldCondition(
                key="workspace_id",
                match=MatchValue(value=normalized_workspace_id),
            )
        ]

        if filter_conditions:
            for key, value in filter_conditions.items():
                if key == "workspace_id":
                    filter_workspace_id = self._extract_workspace_id_from_filter_value(value)
                    if filter_workspace_id != normalized_workspace_id:
                        raise ValueError(
                            "workspace_id filter must match the workspace_id argument"
                        )
                    continue

                match_expression = (
                    MatchAny(any=value["any"])
                    if isinstance(value, dict) and "any" in value
                    else MatchValue(value=value)
                )
                conditions.append(
                    FieldCondition(
                        key=f"metadata.{key}",
                        match=match_expression
                    )
                )
        query_filter = Filter(must=conditions)

        results = self.client.search(
            collection_name=collection_name or self.collection_name,
            query_vector=query_vector,
            limit=limit,
            query_filter=query_filter
        )
        
        formatted_results = []
        for result in results:
            formatted_results.append({
                "id": result.id,
                "score": result.score,
                "text": result.payload.get("text"),
                "metadata": result.payload.get("metadata"),
                "ingested_at": result.payload.get("ingested_at")
            })
        
        return formatted_results
    
    def delete_by_metadata(
        self,
        metadata_key: str,
        metadata_value: Any,
        workspace_id: Optional[str] = None,
    ):
        """Delete points matching metadata criteria."""
        conditions = [
            FieldCondition(
                key=f"metadata.{metadata_key}",
                match=MatchValue(value=metadata_value)
            )
        ]
        if workspace_id is not None:
            normalized_workspace_id = self._normalize_workspace_id(workspace_id)
            conditions.append(
                FieldCondition(
                    key="workspace_id",
                    match=MatchValue(value=normalized_workspace_id),
                )
            )
        filter_condition = Filter(must=conditions)
        
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=filter_condition
        )
        
        logger.info(f"Deleted points with {metadata_key}={metadata_value}")
    
    def get_collection_info(self) -> Dict[str, Any]:
        """Get collection statistics."""
        try:
            info = self.client.get_collection(self.collection_name)
            return {
                "name": self.collection_name,
                "vectors_count": info.vectors_count,
                "points_count": info.points_count,
                "status": info.status
            }
        except Exception as e:
            logger.error(f"Error getting collection info: {e}")
            return {"error": str(e)}


class RAGIngestionService:
    """Main RAG ingestion service coordinating all components."""
    
    def __init__(
        self,
        qdrant_host: str = "localhost",
        qdrant_port: int = 6333,
        collection_name: str = "documents",
        chunk_size: int = 1000,
        chunk_overlap: int = 100,
        embedding_model: str = "nomic-ai/nomic-embed-text-v1.5",
        embedding_provider: str = "local",
        embedding_service_url: str = "http://localhost:8003",
        default_workspace_id: str = DEFAULT_WORKSPACE_ID,
        graph_service: Optional[Any] = None
    ):
        self.chunker = DocumentChunker(chunk_size=chunk_size, overlap=chunk_overlap)
        normalized_provider = embedding_provider.strip().lower()
        if normalized_provider == "service":
            logger.info("Using HTTP embedding service provider")
            self.embedder = HTTPEmbeddingServiceClient(
                service_url=embedding_service_url,
                model_name=embedding_model,
            )
        else:
            logger.info("Using in-process embedding provider")
            self.embedder = NomicEmbedder(model_name=embedding_model)
        self.storage = QdrantStorage(
            host=qdrant_host,
            port=qdrant_port,
            collection_name=collection_name
        )
        self.default_workspace_id = QdrantStorage._normalize_workspace_id(default_workspace_id)
        self.graph_service = graph_service
        
        self.storage.create_collection(self.embedder.dimension)
        logger.info("RAG Ingestion Service initialized")

    def _resolve_workspace_id(
        self,
        workspace_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Resolve a single workspace_id from args/metadata/filters/default."""
        candidates: Dict[str, str] = {}

        if workspace_id is not None:
            candidates["argument"] = QdrantStorage._normalize_workspace_id(workspace_id)

        if metadata and "workspace_id" in metadata:
            candidates["metadata.workspace_id"] = QdrantStorage._normalize_workspace_id(
                metadata["workspace_id"]
            )

        if filters and "workspace_id" in filters:
            candidates["filters.workspace_id"] = (
                QdrantStorage._extract_workspace_id_from_filter_value(filters["workspace_id"])
            )

        if not candidates:
            return self.default_workspace_id

        unique_values = set(candidates.values())
        if len(unique_values) != 1:
            raise ValueError(
                "Conflicting workspace_id values provided "
                f"(received: {candidates})"
            )

        return next(iter(unique_values))
    
    def ingest_document(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
        workspace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Ingest a document: chunk, embed, and store.
        
        Args:
            text: Document text to ingest
            metadata: Optional metadata for the document
            
        Returns:
            Dictionary with ingestion results
        """
        if not text:
            raise ValueError("Text cannot be empty")
        
        if metadata is None:
            metadata = {}

        metadata = metadata.copy()
        resolved_workspace_id = self._resolve_workspace_id(
            workspace_id=workspace_id,
            metadata=metadata,
        )
        metadata["workspace_id"] = resolved_workspace_id
        
        metadata.setdefault("document_id", str(uuid.uuid4()))
        metadata.setdefault("ingestion_timestamp", datetime.utcnow().isoformat())
        
        chunks = self.chunker.chunk_text(text, metadata)
        logger.info(f"Created {len(chunks)} chunks from document")
        
        chunk_texts = [chunk["text"] for chunk in chunks]
        chunk_metadatas = [chunk["metadata"] for chunk in chunks]
        
        embeddings = self.embedder.embed_batch(chunk_texts)
        logger.info(f"Generated {len(embeddings)} embeddings")
        
        point_ids = self.storage.upsert_points(
            chunk_texts,
            embeddings,
            chunk_metadatas,
            workspace_id=resolved_workspace_id,
        )
        logger.info(f"Stored {len(point_ids)} points in Qdrant")
        
        return {
            "status": "success",
            "document_id": metadata["document_id"],
            "chunks_created": len(chunks),
            "points_stored": len(point_ids),
            "point_ids": point_ids,
            "workspace_id": resolved_workspace_id,
            "metadata": metadata
        }
    
    def ingest_documents_batch(
        self,
        documents: List[Dict[str, Any]],
        workspace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Ingest multiple documents.
        
        Args:
            documents: List of documents, each with 'text' and optional 'metadata'
            
        Returns:
            Dictionary with batch ingestion results
        """
        results = []
        total_chunks = 0
        total_points = 0
        
        for doc in documents:
            text = doc.get("text")
            metadata = doc.get("metadata", {})
            
            try:
                result = self.ingest_document(
                    text,
                    metadata,
                    workspace_id=workspace_id,
                )
                results.append(result)
                total_chunks += result["chunks_created"]
                total_points += result["points_stored"]
            except Exception as e:
                logger.error(f"Error ingesting document: {e}")
                results.append({
                    "status": "error",
                    "error": str(e),
                    "metadata": metadata
                })
        
        return {
            "status": "success",
            "documents_processed": len(documents),
            "total_chunks": total_chunks,
            "total_points": total_points,
            "results": results
        }
    
    def search_documents(
        self,
        query: str,
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        collection_name: Optional[str] = None,
        workspace_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search for relevant documents.
        
        Args:
            query: Search query text
            limit: Maximum number of results
            filters: Optional metadata filters
            collection_name: Optional Qdrant collection override
            
        Returns:
            List of search results
        """
        resolved_workspace_id = self._resolve_workspace_id(
            workspace_id=workspace_id,
            filters=filters,
        )
        query_embedding = self.embedder.embed_text(query)
        results = self.storage.search(
            query_embedding,
            workspace_id=resolved_workspace_id,
            limit=limit,
            filter_conditions=filters,
            collection_name=collection_name,
        )
        return results

    def semantic_search(
        self,
        query: str,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        collection_name: Optional[str] = None,
        workspace_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Perform semantic similarity search over a Qdrant collection.

        Args:
            query: Search query text
            top_k: Maximum number of nearest neighbors to return
            filters: Optional metadata filters (equality or {"any": [...]})
            collection_name: Optional Qdrant collection override

        Returns:
            List of semantic search results ordered by similarity score
        """
        if top_k < 1:
            raise ValueError("top_k must be greater than 0")

        results = self.search_documents(
            query=query,
            limit=top_k,
            filters=filters,
            collection_name=collection_name,
            workspace_id=workspace_id,
        )
        return results
    
    def search_with_graph_enrichment(
        self,
        query: str,
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        graph_depth: int = 1,
        graph_limit: int = 10,
        include_entity_context: bool = True,
        workspace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Search for relevant documents with graph-based context enrichment.
        
        This method:
        1. Performs vector similarity search to find relevant documents
        2. Extracts entities from the query and search results
        3. Queries the knowledge graph for related entities and relationships
        4. Augments the results with graph context
        
        Args:
            query: Search query text
            limit: Maximum number of vector search results
            filters: Optional metadata filters for vector search
            graph_depth: Maximum depth for graph traversal (1-3)
            graph_limit: Maximum number of graph neighbors per entity
            include_entity_context: Whether to include entity descriptions
            
        Returns:
            Dictionary with vector results and enriched graph context
        """
        if not self.graph_service:
            logger.warning("Graph service not available, falling back to standard search")
            return {
                "query": query,
                "vector_results": self.search_documents(
                    query,
                    limit,
                    filters,
                    workspace_id=workspace_id,
                ),
                "graph_context": None,
                "enriched": False
            }
        
        # Step 1: Perform vector similarity search
        logger.info(f"Performing vector search for query: {query}")
        resolved_workspace_id = self._resolve_workspace_id(
            workspace_id=workspace_id,
            filters=filters,
        )
        query_embedding = self.embedder.embed_text(query)
        vector_results = self.storage.search(
            query_embedding,
            workspace_id=resolved_workspace_id,
            limit=limit,
            filter_conditions=filters,
        )
        
        # Step 2: Extract entities from query
        logger.info("Extracting entities from query")
        query_entities = self.graph_service.extract_entities(query)
        
        # Step 3: Extract entities from top search results
        result_entities = []
        for result in vector_results[:3]:  # Only analyze top 3 results
            text = result.get("text", "")
            if text:
                entities = self.graph_service.extract_entities(text)
                result_entities.extend(entities)
        
        # Combine and deduplicate entities
        all_entities = query_entities + result_entities
        unique_entity_names = set()
        unique_entities = []
        for entity in all_entities:
            name = entity["text"].lower().strip()
            if name not in unique_entity_names:
                unique_entity_names.add(name)
                unique_entities.append(entity)
        
        logger.info(f"Found {len(unique_entities)} unique entities")
        
        # Step 4: Query graph for each entity's neighborhood
        graph_context = {
            "entities": [],
            "relationships": [],
            "subgraphs": []
        }
        
        for entity in unique_entities[:5]:  # Limit to top 5 entities to avoid overload
            try:
                # Get entity neighbors from graph
                neighbors_data = self.graph_service.get_neighbors(
                    entity_name=entity["text"],
                    entity_type=entity["type"],
                    max_depth=graph_depth,
                    limit=graph_limit
                )
                
                if neighbors_data["neighbors_count"] > 0:
                    graph_context["entities"].append({
                        "name": entity["text"],
                        "type": entity["type"],
                        "neighbor_count": neighbors_data["neighbors_count"]
                    })
                    
                    # Collect relationships
                    for neighbor in neighbors_data["neighbors"]:
                        graph_context["relationships"].append({
                            "source": entity["text"],
                            "source_type": entity["type"],
                            "target": neighbor["name"],
                            "target_type": neighbor["type"],
                            "relation_types": neighbor["relation_types"],
                            "distance": neighbor["distance"]
                        })
                    
                    # Store subgraph
                    graph_context["subgraphs"].append({
                        "root": entity["text"],
                        "neighbors": neighbors_data["neighbors"]
                    })
                    
            except Exception as e:
                logger.warning(f"Error querying graph for entity {entity['text']}: {e}")
        
        # Step 5: Enrich vector results with graph context
        enriched_results = []
        for result in vector_results:
            enriched_result = result.copy()
            
            # Find related graph entities for this result
            related_entities = []
            for entity in unique_entities:
                if entity["text"].lower() in result.get("text", "").lower():
                    # Find this entity's neighbors in graph context
                    for subgraph in graph_context["subgraphs"]:
                        if subgraph["root"].lower() == entity["text"].lower():
                            related_entities.append({
                                "entity": entity["text"],
                                "type": entity["type"],
                                "neighbor_count": len(subgraph["neighbors"]),
                                "neighbors": subgraph["neighbors"][:3]  # Top 3 neighbors
                            })
            
            enriched_result["graph_entities"] = related_entities
            enriched_results.append(enriched_result)
        
        logger.info(f"Enriched {len(enriched_results)} results with graph context")
        
        return {
            "query": query,
            "vector_results": enriched_results,
            "graph_context": graph_context,
            "enriched": True,
            "stats": {
                "vector_results_count": len(vector_results),
                "entities_found": len(unique_entities),
                "entities_in_graph": len(graph_context["entities"]),
                "relationships_found": len(graph_context["relationships"]),
                "subgraphs": len(graph_context["subgraphs"])
            }
        }
    
    def format_graph_context_for_llm(
        self,
        graph_context: Dict[str, Any]
    ) -> str:
        """
        Format graph context into a human-readable string for LLM prompting.
        
        Args:
            graph_context: Graph context dictionary from search_with_graph_enrichment
            
        Returns:
            Formatted context string
        """
        if not graph_context or not graph_context.get("entities"):
            return ""
        
        context_parts = []
        
        # Add entities summary
        entities = graph_context.get("entities", [])
        if entities:
            context_parts.append("Knowledge Graph Entities:")
            for entity in entities:
                context_parts.append(
                    f"  - {entity['name']} ({entity['type']}) "
                    f"with {entity['neighbor_count']} related entities"
                )
        
        # Add relationships summary
        relationships = graph_context.get("relationships", [])
        if relationships:
            context_parts.append("\nEntity Relationships:")
            # Group by source entity
            rel_by_source = {}
            for rel in relationships:
                source = rel["source"]
                if source not in rel_by_source:
                    rel_by_source[source] = []
                rel_by_source[source].append(rel)
            
            for source, rels in rel_by_source.items():
                context_parts.append(f"  {source}:")
                for rel in rels[:5]:  # Limit to top 5 per source
                    rel_types = ", ".join(rel["relation_types"])
                    context_parts.append(
                        f"    - {rel_types} → {rel['target']} ({rel['target_type']})"
                    )
        
        return "\n".join(context_parts)
    
    def delete_document(self, document_id: str, workspace_id: Optional[str] = None):
        """Delete all chunks of a document by document_id."""
        resolved_workspace_id = self._resolve_workspace_id(workspace_id=workspace_id)
        self.storage.delete_by_metadata(
            "document_id",
            document_id,
            workspace_id=resolved_workspace_id,
        )
        logger.info(f"Deleted document: {document_id}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get RAG service statistics."""
        return self.storage.get_collection_info()

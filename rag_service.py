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

from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue
)

logger = logging.getLogger(__name__)


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
        metadatas: List[Dict[str, Any]]
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
        points = []
        point_ids = []
        
        for text, embedding, metadata in zip(texts, embeddings, metadatas):
            point_id = str(uuid.uuid4())
            point_ids.append(point_id)
            
            payload = {
                "text": text,
                "metadata": metadata,
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
        limit: int = 10,
        filter_conditions: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for similar documents.
        
        Args:
            query_vector: Query embedding vector
            limit: Maximum number of results
            filter_conditions: Optional metadata filters
            
        Returns:
            List of search results with text, metadata, and score
        """
        query_filter = None
        if filter_conditions:
            conditions = []
            for key, value in filter_conditions.items():
                conditions.append(
                    FieldCondition(
                        key=f"metadata.{key}",
                        match=MatchValue(value=value)
                    )
                )
            query_filter = Filter(must=conditions)
        
        results = self.client.search(
            collection_name=self.collection_name,
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
    
    def delete_by_metadata(self, metadata_key: str, metadata_value: Any):
        """Delete points matching metadata criteria."""
        filter_condition = Filter(
            must=[
                FieldCondition(
                    key=f"metadata.{metadata_key}",
                    match=MatchValue(value=metadata_value)
                )
            ]
        )
        
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
        embedding_model: str = "nomic-ai/nomic-embed-text-v1.5"
    ):
        self.chunker = DocumentChunker(chunk_size=chunk_size, overlap=chunk_overlap)
        self.embedder = NomicEmbedder(model_name=embedding_model)
        self.storage = QdrantStorage(
            host=qdrant_host,
            port=qdrant_port,
            collection_name=collection_name
        )
        
        self.storage.create_collection(self.embedder.dimension)
        logger.info("RAG Ingestion Service initialized")
    
    def ingest_document(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None
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
        
        metadata.setdefault("document_id", str(uuid.uuid4()))
        metadata.setdefault("ingestion_timestamp", datetime.utcnow().isoformat())
        
        chunks = self.chunker.chunk_text(text, metadata)
        logger.info(f"Created {len(chunks)} chunks from document")
        
        chunk_texts = [chunk["text"] for chunk in chunks]
        chunk_metadatas = [chunk["metadata"] for chunk in chunks]
        
        embeddings = self.embedder.embed_batch(chunk_texts)
        logger.info(f"Generated {len(embeddings)} embeddings")
        
        point_ids = self.storage.upsert_points(chunk_texts, embeddings, chunk_metadatas)
        logger.info(f"Stored {len(point_ids)} points in Qdrant")
        
        return {
            "status": "success",
            "document_id": metadata["document_id"],
            "chunks_created": len(chunks),
            "points_stored": len(point_ids),
            "point_ids": point_ids,
            "metadata": metadata
        }
    
    def ingest_documents_batch(
        self,
        documents: List[Dict[str, Any]]
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
                result = self.ingest_document(text, metadata)
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
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for relevant documents.
        
        Args:
            query: Search query text
            limit: Maximum number of results
            filters: Optional metadata filters
            
        Returns:
            List of search results
        """
        query_embedding = self.embedder.embed_text(query)
        results = self.storage.search(query_embedding, limit=limit, filter_conditions=filters)
        return results
    
    def delete_document(self, document_id: str):
        """Delete all chunks of a document by document_id."""
        self.storage.delete_by_metadata("document_id", document_id)
        logger.info(f"Deleted document: {document_id}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get RAG service statistics."""
        return self.storage.get_collection_info()

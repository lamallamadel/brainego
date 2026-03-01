#!/usr/bin/env python3
"""
Memory service using Mem0 with Qdrant backend and Redis for key-value storage.
Provides automatic fact extraction from conversations and memory retrieval with
cosine similarity + temporal decay scoring.
"""

import os
import time
import json
import uuid
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime, timezone
from mem0 import Memory
from qdrant_client import QdrantClient
from qdrant_client.http import models
import redis
import numpy as np

from memory_scoring import combined_memory_score, normalize_weights

logger = logging.getLogger(__name__)


class MemoryService:
    """
    Memory service with Mem0, Qdrant, and Redis.
    
    Features:
    - Automatic fact extraction from conversations
    - Cosine similarity search in Qdrant
    - Temporal decay scoring (recency bias)
    - Redis for key-value storage and metadata
    """
    
    def __init__(
        self,
        qdrant_host: str = "localhost",
        qdrant_port: int = 6333,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_db: int = 0,
        memory_collection: str = "memories",
        embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
        temporal_decay_factor: float = 0.1,
        cosine_weight: float = 0.7,
        temporal_weight: float = 0.3
    ):
        """
        Initialize Memory Service.
        
        Args:
            qdrant_host: Qdrant host
            qdrant_port: Qdrant port
            redis_host: Redis host
            redis_port: Redis port
            redis_db: Redis database number
            memory_collection: Qdrant collection name for memories
            embedding_model: Model for embeddings
            temporal_decay_factor: Factor for temporal decay (higher = faster decay)
            cosine_weight: Relative weight for cosine similarity score
            temporal_weight: Relative weight for recency score
        """
        self.qdrant_host = qdrant_host
        self.qdrant_port = qdrant_port
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.memory_collection = memory_collection
        self.embedding_model = embedding_model
        self.temporal_decay_factor = temporal_decay_factor
        self.cosine_weight, self.temporal_weight = normalize_weights(
            cosine_weight, temporal_weight
        )
        
        logger.info("Initializing Memory Service...")
        
        # Initialize Qdrant client
        self.qdrant_client = QdrantClient(host=qdrant_host, port=qdrant_port)
        
        # Initialize Redis client
        self.redis_client = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            decode_responses=True
        )
        
        # Test connections
        try:
            self.redis_client.ping()
            logger.info("Redis connection successful")
        except Exception as e:
            logger.error(f"Redis connection failed: {e}")
            raise
        
        # Configure Mem0 with Qdrant and embeddings
        config = {
            "vector_store": {
                "provider": "qdrant",
                "config": {
                    "host": qdrant_host,
                    "port": qdrant_port,
                    "collection_name": memory_collection,
                }
            },
            "embedder": {
                "provider": "huggingface",
                "config": {
                    "model": embedding_model
                }
            },
            "llm": {
                "provider": "openai",
                "config": {
                    "model": "gpt-3.5-turbo",
                    "temperature": 0.1,
                    "max_tokens": 1000
                }
            },
            "version": "v1.1"
        }
        
        # Initialize Mem0
        try:
            self.memory = Memory.from_config(config)
            logger.info("Mem0 initialized successfully")
        except Exception as e:
            logger.warning(f"Mem0 initialization with LLM failed: {e}")
            # Fallback to basic configuration without LLM
            config_basic = {
                "vector_store": {
                    "provider": "qdrant",
                    "config": {
                        "host": qdrant_host,
                        "port": qdrant_port,
                        "collection_name": memory_collection,
                    }
                },
                "embedder": {
                    "provider": "huggingface",
                    "config": {
                        "model": embedding_model
                    }
                }
            }
            self.memory = Memory.from_config(config_basic)
            logger.info("Mem0 initialized with basic configuration (no LLM)")
        
        # Ensure collection exists
        self._ensure_collection()
        
        logger.info("Memory Service initialization complete")
    
    def _ensure_collection(self):
        """Ensure the memory collection exists in Qdrant."""
        try:
            collections = self.qdrant_client.get_collections().collections
            collection_names = [c.name for c in collections]
            
            if self.memory_collection not in collection_names:
                # Get embedding dimension from the model
                from sentence_transformers import SentenceTransformer
                model = SentenceTransformer(self.embedding_model)
                vector_size = model.get_sentence_embedding_dimension()
                
                self.qdrant_client.create_collection(
                    collection_name=self.memory_collection,
                    vectors_config=models.VectorParams(
                        size=vector_size,
                        distance=models.Distance.COSINE
                    )
                )
                logger.info(f"Created collection '{self.memory_collection}' with dimension {vector_size}")
            else:
                logger.info(f"Collection '{self.memory_collection}' already exists")
        except Exception as e:
            logger.error(f"Error ensuring collection: {e}")
    
    def add_memory(
        self,
        messages: List[Dict[str, str]],
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Add memories from conversation messages with automatic fact extraction.
        
        Args:
            messages: List of conversation messages [{"role": "user/assistant", "content": "..."}]
            user_id: Optional user identifier for personalized memories
            metadata: Optional metadata to store with the memory
        
        Returns:
            Dictionary with memory IDs and extracted facts
        """
        try:
            memory_id = str(uuid.uuid4())
            timestamp = datetime.now(timezone.utc).isoformat()
            
            # Convert messages to text for Mem0
            conversation_text = "\n".join([
                f"{msg['role']}: {msg['content']}"
                for msg in messages
            ])
            
            # Use Mem0 to add memory (it will extract facts automatically)
            mem0_user_id = user_id or "default_user"
            
            try:
                # Try to add with Mem0 (may extract multiple facts)
                result = self.memory.add(
                    messages=messages,
                    user_id=mem0_user_id,
                    metadata=metadata or {}
                )
                
                # Store metadata in Redis
                redis_key = f"memory:{memory_id}"
                redis_data = {
                    "memory_id": memory_id,
                    "user_id": mem0_user_id,
                    "timestamp": timestamp,
                    "messages": json.dumps(messages),
                    "metadata": json.dumps(metadata or {}),
                    "mem0_result": json.dumps(result) if result else "{}"
                }
                self.redis_client.hset(redis_key, mapping=redis_data)
                
                # Set expiration (30 days)
                self.redis_client.expire(redis_key, 30 * 24 * 60 * 60)
                
                logger.info(f"Memory added successfully: {memory_id}")
                
                return {
                    "status": "success",
                    "memory_id": memory_id,
                    "timestamp": timestamp,
                    "user_id": mem0_user_id,
                    "facts_extracted": len(result) if isinstance(result, list) else 1,
                    "mem0_result": result
                }
            
            except Exception as e:
                logger.warning(f"Mem0 add failed, using fallback: {e}")
                # Fallback: manually create embeddings and store
                return self._add_memory_fallback(
                    memory_id, messages, mem0_user_id, metadata, timestamp
                )
        
        except Exception as e:
            logger.error(f"Error adding memory: {e}", exc_info=True)
            raise
    
    def _add_memory_fallback(
        self,
        memory_id: str,
        messages: List[Dict[str, str]],
        user_id: str,
        metadata: Optional[Dict[str, Any]],
        timestamp: str
    ) -> Dict[str, Any]:
        """Fallback method to add memory without Mem0 fact extraction."""
        from sentence_transformers import SentenceTransformer
        
        # Create embedding from conversation
        conversation_text = "\n".join([
            f"{msg['role']}: {msg['content']}"
            for msg in messages
        ])
        
        model = SentenceTransformer(self.embedding_model)
        embedding = model.encode(conversation_text).tolist()
        
        # Store in Qdrant
        point = models.PointStruct(
            id=memory_id,
            vector=embedding,
            payload={
                "memory_id": memory_id,
                "user_id": user_id,
                "text": conversation_text,
                "timestamp": timestamp,
                "metadata": metadata or {},
                "messages": messages
            }
        )
        
        self.qdrant_client.upsert(
            collection_name=self.memory_collection,
            points=[point]
        )
        
        # Store in Redis
        redis_key = f"memory:{memory_id}"
        redis_data = {
            "memory_id": memory_id,
            "user_id": user_id,
            "timestamp": timestamp,
            "messages": json.dumps(messages),
            "metadata": json.dumps(metadata or {}),
            "text": conversation_text
        }
        self.redis_client.hset(redis_key, mapping=redis_data)
        self.redis_client.expire(redis_key, 30 * 24 * 60 * 60)
        
        logger.info(f"Memory added via fallback: {memory_id}")
        
        return {
            "status": "success",
            "memory_id": memory_id,
            "timestamp": timestamp,
            "user_id": user_id,
            "facts_extracted": 1,
            "method": "fallback"
        }
    
    def search_memory(
        self,
        query: str,
        user_id: Optional[str] = None,
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        use_temporal_decay: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Search memories with cosine similarity + temporal decay scoring.
        
        Args:
            query: Search query text
            user_id: Optional user ID to filter memories
            limit: Maximum number of results
            filters: Optional metadata filters
            use_temporal_decay: Apply temporal decay to scores
        
        Returns:
            List of memories with combined scores
        """
        try:
            mem0_user_id = user_id or "default_user"
            
            # Try Mem0 search first
            try:
                mem0_results = self.memory.search(
                    query=query,
                    user_id=mem0_user_id,
                    limit=limit
                )
                
                if mem0_results:
                    # Enhance results with temporal decay
                    enhanced_results = []
                    current_time = datetime.now(timezone.utc)
                    
                    for result in mem0_results:
                        # Get memory details from Redis if available
                        memory_id = result.get("id") or result.get("memory_id")
                        
                        if memory_id:
                            redis_key = f"memory:{memory_id}"
                            redis_data = self.redis_client.hgetall(redis_key)
                            
                            if redis_data:
                                timestamp_str = redis_data.get("timestamp")
                                if timestamp_str and use_temporal_decay:
                                    memory_time = datetime.fromisoformat(timestamp_str)
                                    time_diff_hours = (current_time - memory_time).total_seconds() / 3600
                                else:
                                    time_diff_hours = 0.0

                                parsed_metadata = json.loads(redis_data.get("metadata", "{}"))
                                if not self._matches_metadata_filters(parsed_metadata, filters):
                                    continue

                                cosine_score = result.get("score", 0.5)
                                combined_score, cosine_score, temporal_score = combined_memory_score(
                                    cosine_similarity=cosine_score,
                                    age_hours=time_diff_hours if use_temporal_decay else 0.0,
                                    temporal_decay_factor=self.temporal_decay_factor,
                                    similarity_weight=self.cosine_weight,
                                    recency_weight=self.temporal_weight,
                                )
                                
                                enhanced_results.append({
                                    "memory_id": memory_id,
                                    "text": result.get("memory", result.get("text", "")),
                                    "score": round(combined_score, 4),
                                    "cosine_score": round(cosine_score, 4),
                                    "temporal_score": round(temporal_score, 4),
                                    "timestamp": redis_data.get("timestamp"),
                                    "user_id": redis_data.get("user_id"),
                                    "metadata": parsed_metadata,
                                    "messages": json.loads(redis_data.get("messages", "[]"))
                                })
                        else:
                            # No Redis data, use Mem0 result as-is
                            result_metadata = result.get("metadata", {})
                            if not self._matches_metadata_filters(result_metadata, filters):
                                continue
                            enhanced_results.append({
                                "text": result.get("memory", result.get("text", "")),
                                "score": result.get("score", 0.5),
                                "metadata": result_metadata
                            })
                    
                    # Sort by combined score
                    enhanced_results.sort(key=lambda x: x.get("score", 0), reverse=True)
                    
                    logger.info(f"Memory search via Mem0: {len(enhanced_results)} results")
                    return enhanced_results[:limit]
            
            except Exception as e:
                logger.warning(f"Mem0 search failed, using fallback: {e}")
            
            # Fallback: direct Qdrant search
            return self._search_memory_fallback(query, user_id, limit, filters, use_temporal_decay)
        
        except Exception as e:
            logger.error(f"Error searching memory: {e}", exc_info=True)
            raise

    @staticmethod
    def _matches_metadata_filters(
        metadata: Optional[Dict[str, Any]],
        filters: Optional[Dict[str, Any]],
    ) -> bool:
        """Return True when metadata satisfies equality/any filter clauses."""
        if not filters:
            return True

        effective_metadata = metadata or {}
        for key, expected in filters.items():
            actual = effective_metadata.get(key)
            if isinstance(expected, dict) and "any" in expected:
                allowed_values = set(expected.get("any", []))
                if actual not in allowed_values:
                    return False
                continue
            if actual != expected:
                return False
        return True
    
    def _search_memory_fallback(
        self,
        query: str,
        user_id: Optional[str],
        limit: int,
        filters: Optional[Dict[str, Any]],
        use_temporal_decay: bool
    ) -> List[Dict[str, Any]]:
        """Fallback method for memory search using direct Qdrant query."""
        from sentence_transformers import SentenceTransformer
        
        # Generate query embedding
        model = SentenceTransformer(self.embedding_model)
        query_embedding = model.encode(query).tolist()
        
        # Build Qdrant filter
        qdrant_filter = None
        if user_id or filters:
            must_conditions = []
            
            if user_id:
                must_conditions.append(
                    models.FieldCondition(
                        key="user_id",
                        match=models.MatchValue(value=user_id)
                    )
                )
            
            if filters:
                for key, value in filters.items():
                    must_conditions.append(
                        models.FieldCondition(
                            key=f"metadata.{key}",
                            match=models.MatchValue(value=value)
                        )
                    )
            
            if must_conditions:
                qdrant_filter = models.Filter(must=must_conditions)
        
        # Search in Qdrant
        search_results = self.qdrant_client.search(
            collection_name=self.memory_collection,
            query_vector=query_embedding,
            limit=limit * 2,  # Get more for temporal filtering
            query_filter=qdrant_filter
        )
        
        # Apply temporal decay
        results = []
        current_time = datetime.now(timezone.utc)
        
        for hit in search_results:
            cosine_score = hit.score
            payload = hit.payload
            
            timestamp_str = payload.get("timestamp")
            if timestamp_str and use_temporal_decay:
                try:
                    memory_time = datetime.fromisoformat(timestamp_str)
                    time_diff_hours = (current_time - memory_time).total_seconds() / 3600
                except Exception:
                    time_diff_hours = 0.0
            else:
                time_diff_hours = 0.0

            combined_score, cosine_score, temporal_score = combined_memory_score(
                cosine_similarity=cosine_score,
                age_hours=time_diff_hours if use_temporal_decay else 0.0,
                temporal_decay_factor=self.temporal_decay_factor,
                similarity_weight=self.cosine_weight,
                recency_weight=self.temporal_weight,
            )
            
            results.append({
                "memory_id": payload.get("memory_id", str(hit.id)),
                "text": payload.get("text", ""),
                "score": round(combined_score, 4),
                "cosine_score": round(cosine_score, 4),
                "temporal_score": round(temporal_score, 4),
                "timestamp": timestamp_str,
                "user_id": payload.get("user_id"),
                "metadata": payload.get("metadata", {}),
                "messages": payload.get("messages", [])
            })
        
        # Sort by combined score and limit
        results.sort(key=lambda x: x["score"], reverse=True)
        
        logger.info(f"Memory search via fallback: {len(results[:limit])} results")
        return results[:limit]
    
    def forget_memory(
        self,
        memory_id: str
    ) -> Dict[str, Any]:
        """
        Delete a memory by ID.
        
        Args:
            memory_id: Memory ID to delete
        
        Returns:
            Deletion status
        """
        try:
            # Delete from Qdrant
            try:
                self.qdrant_client.delete(
                    collection_name=self.memory_collection,
                    points_selector=models.PointIdsList(
                        points=[memory_id]
                    )
                )
                logger.info(f"Deleted memory from Qdrant: {memory_id}")
            except Exception as e:
                logger.warning(f"Could not delete from Qdrant: {e}")
            
            # Delete from Redis
            redis_key = f"memory:{memory_id}"
            deleted = self.redis_client.delete(redis_key)
            
            if deleted:
                logger.info(f"Deleted memory from Redis: {memory_id}")
            else:
                logger.warning(f"Memory not found in Redis: {memory_id}")
            
            return {
                "status": "success",
                "memory_id": memory_id,
                "message": "Memory deleted successfully"
            }
        
        except Exception as e:
            logger.error(f"Error deleting memory: {e}", exc_info=True)
            raise
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """Get memory system statistics."""
        try:
            # Qdrant stats
            collection_info = self.qdrant_client.get_collection(self.memory_collection)
            
            # Redis stats
            redis_keys = self.redis_client.keys("memory:*")
            redis_memory_count = len(redis_keys)
            
            return {
                "collection_name": self.memory_collection,
                "qdrant_points": collection_info.points_count,
                "redis_memories": redis_memory_count,
                "vector_dimension": collection_info.config.params.vectors.size,
                "distance_metric": collection_info.config.params.vectors.distance.name
            }
        
        except Exception as e:
            logger.error(f"Error getting memory stats: {e}", exc_info=True)
            raise

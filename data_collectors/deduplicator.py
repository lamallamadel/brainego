#!/usr/bin/env python3
"""
Deduplication Service
Implements hash-based and cosine similarity deduplication.
"""

import hashlib
import logging
from typing import List, Dict, Any, Set, Tuple
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)


class Deduplicator:
    """Deduplicates documents using hash and cosine similarity."""
    
    def __init__(self, similarity_threshold: float = 0.95):
        """
        Initialize deduplicator.
        
        Args:
            similarity_threshold: Cosine similarity threshold for duplicates (0-1)
        """
        self.similarity_threshold = similarity_threshold
        self.seen_hashes: Set[str] = set()
        self.vectorizer = TfidfVectorizer(
            max_features=1000,
            stop_words='english',
            ngram_range=(1, 2)
        )
        logger.info(f"Initialized Deduplicator with threshold={similarity_threshold}")
    
    def deduplicate_batch(
        self,
        documents: List[Dict[str, Any]],
        use_hash: bool = True,
        use_similarity: bool = True
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Deduplicate a batch of documents.
        
        Args:
            documents: List of documents to deduplicate
            use_hash: Whether to use hash-based deduplication
            use_similarity: Whether to use similarity-based deduplication
            
        Returns:
            Tuple of (unique documents, stats)
        """
        if not documents:
            return [], {"total": 0, "unique": 0, "duplicates": 0}
        
        total_docs = len(documents)
        unique_docs = []
        hash_duplicates = 0
        similarity_duplicates = 0
        
        if use_hash:
            documents, hash_duplicates = self._hash_based_deduplication(documents)
        
        if use_similarity and len(documents) > 1:
            documents, similarity_duplicates = self._similarity_based_deduplication(documents)
        
        unique_docs = documents
        total_duplicates = hash_duplicates + similarity_duplicates
        
        stats = {
            "total": total_docs,
            "unique": len(unique_docs),
            "duplicates": total_duplicates,
            "hash_duplicates": hash_duplicates,
            "similarity_duplicates": similarity_duplicates,
            "deduplication_rate": total_duplicates / total_docs if total_docs > 0 else 0
        }
        
        logger.info(
            f"Deduplication complete: {total_docs} -> {len(unique_docs)} "
            f"({total_duplicates} duplicates, {stats['deduplication_rate']:.2%} rate)"
        )
        
        return unique_docs, stats
    
    def _hash_based_deduplication(
        self,
        documents: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Remove exact duplicates using content hashing.
        
        Args:
            documents: List of documents
            
        Returns:
            Tuple of (unique documents, duplicate count)
        """
        unique_docs = []
        duplicates = 0
        
        for doc in documents:
            content_hash = self._compute_hash(doc.get("text", ""))
            
            if content_hash not in self.seen_hashes:
                self.seen_hashes.add(content_hash)
                unique_docs.append(doc)
            else:
                duplicates += 1
        
        logger.info(f"Hash deduplication: removed {duplicates} exact duplicates")
        return unique_docs, duplicates
    
    def _similarity_based_deduplication(
        self,
        documents: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Remove near-duplicates using cosine similarity.
        
        Args:
            documents: List of documents
            
        Returns:
            Tuple of (unique documents, duplicate count)
        """
        if len(documents) <= 1:
            return documents, 0
        
        texts = [doc.get("text", "") for doc in documents]
        
        try:
            tfidf_matrix = self.vectorizer.fit_transform(texts)
            
            similarities = cosine_similarity(tfidf_matrix)
            
            keep_indices = set(range(len(documents)))
            
            for i in range(len(documents)):
                if i not in keep_indices:
                    continue
                
                for j in range(i + 1, len(documents)):
                    if j not in keep_indices:
                        continue
                    
                    if similarities[i, j] >= self.similarity_threshold:
                        keep_indices.discard(j)
            
            unique_docs = [documents[i] for i in sorted(keep_indices)]
            duplicates = len(documents) - len(unique_docs)
            
            logger.info(
                f"Similarity deduplication: removed {duplicates} near-duplicates "
                f"(threshold={self.similarity_threshold})"
            )
            
            return unique_docs, duplicates
            
        except Exception as e:
            logger.error(f"Error in similarity deduplication: {e}")
            return documents, 0
    
    def _compute_hash(self, text: str) -> str:
        """Compute SHA256 hash of text."""
        normalized_text = text.strip().lower()
        return hashlib.sha256(normalized_text.encode('utf-8')).hexdigest()
    
    def reset_hash_cache(self):
        """Reset the seen hashes cache."""
        self.seen_hashes.clear()
        logger.info("Reset hash cache")
    
    def get_cache_size(self) -> int:
        """Get the number of cached hashes."""
        return len(self.seen_hashes)

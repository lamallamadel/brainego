#!/usr/bin/env python3
"""
Graph Service: Neo4j-based knowledge graph with NER and relation extraction.

Features:
- Neo4j Community deployment with defined schema
- Named Entity Recognition (NER) pipeline
- Relation construction (co-occurrence + explicit extraction)
- Graph query API endpoints
"""

import os
import logging
import re
from typing import List, Dict, Any, Optional, Set, Tuple
from datetime import datetime
from collections import defaultdict

from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, Neo4jError
import spacy
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


class GraphService:
    """
    Graph service for entity extraction, relation construction, and graph queries.
    
    Schema:
    - Nodes: Project, Person, Concept, Document, Problem, Lesson
    - Relations: WORKS_ON, RELATES_TO, CAUSED_BY, SOLVED_BY, LEARNED_FROM
    """
    
    # Node types
    NODE_TYPES = ["Project", "Person", "Concept", "Document", "Problem", "Lesson"]
    
    # Relation types
    RELATION_TYPES = [
        "WORKS_ON",      # Person -> Project
        "RELATES_TO",    # Any -> Any (general association)
        "CAUSED_BY",     # Problem -> Concept/Action
        "SOLVED_BY",     # Problem -> Person/Concept
        "LEARNED_FROM"   # Lesson -> Problem/Project
    ]
    
    # Co-occurrence window size (in sentences)
    COOCCURRENCE_WINDOW = 3
    
    def __init__(
        self,
        neo4j_uri: str = "bolt://localhost:7687",
        neo4j_user: str = "neo4j",
        neo4j_password: str = "password",
        embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
        spacy_model: str = "en_core_web_sm"
    ):
        """
        Initialize Graph Service.
        
        Args:
            neo4j_uri: Neo4j connection URI
            neo4j_user: Neo4j username
            neo4j_password: Neo4j password
            embedding_model: Model for entity embeddings
            spacy_model: SpaCy model for NER
        """
        self.neo4j_uri = neo4j_uri
        self.neo4j_user = neo4j_user
        self.neo4j_password = neo4j_password
        
        # Initialize Neo4j driver
        logger.info(f"Connecting to Neo4j at {neo4j_uri}...")
        self.driver = GraphDatabase.driver(
            neo4j_uri,
            auth=(neo4j_user, neo4j_password),
            max_connection_lifetime=3600
        )
        
        # Verify connection
        self._verify_connection()
        
        # Initialize schema
        self._initialize_schema()
        
        # Load SpaCy model for NER
        logger.info(f"Loading SpaCy model: {spacy_model}...")
        try:
            self.nlp = spacy.load(spacy_model)
        except OSError:
            logger.warning(f"SpaCy model {spacy_model} not found. Downloading...")
            import subprocess
            subprocess.run(["python", "-m", "spacy", "download", spacy_model])
            self.nlp = spacy.load(spacy_model)
        
        # Load embedding model
        logger.info(f"Loading embedding model: {embedding_model}...")
        self.embedding_model = SentenceTransformer(embedding_model)
        
        logger.info("Graph Service initialized successfully")
    
    def _verify_connection(self):
        """Verify Neo4j connection."""
        try:
            with self.driver.session() as session:
                result = session.run("RETURN 1 as num")
                record = result.single()
                if record["num"] == 1:
                    logger.info("Neo4j connection verified")
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            raise
    
    def _initialize_schema(self):
        """Initialize graph schema with constraints and indexes."""
        with self.driver.session() as session:
            # Create uniqueness constraints for node types
            for node_type in self.NODE_TYPES:
                try:
                    session.run(
                        f"CREATE CONSTRAINT {node_type.lower()}_name_unique IF NOT EXISTS "
                        f"FOR (n:{node_type}) REQUIRE n.name IS UNIQUE"
                    )
                    logger.info(f"Created constraint for {node_type}")
                except Neo4jError as e:
                    logger.debug(f"Constraint for {node_type} may already exist: {e}")
            
            # Create indexes for better query performance
            for node_type in self.NODE_TYPES:
                try:
                    session.run(
                        f"CREATE INDEX {node_type.lower()}_name_index IF NOT EXISTS "
                        f"FOR (n:{node_type}) ON (n.name)"
                    )
                    logger.info(f"Created index for {node_type}")
                except Neo4jError as e:
                    logger.debug(f"Index for {node_type} may already exist: {e}")
            
            # Create full-text search indexes
            try:
                session.run(
                    "CREATE FULLTEXT INDEX entity_search IF NOT EXISTS "
                    "FOR (n:Project|Person|Concept|Document|Problem|Lesson) "
                    "ON EACH [n.name, n.description]"
                )
                logger.info("Created full-text search index")
            except Neo4jError as e:
                logger.debug(f"Full-text index may already exist: {e}")
        
        logger.info("Graph schema initialized")
    
    def extract_entities(self, text: str) -> List[Dict[str, Any]]:
        """
        Extract entities from text using NER pipeline.
        
        Args:
            text: Input text
        
        Returns:
            List of extracted entities with type, text, and metadata
        """
        doc = self.nlp(text)
        entities = []
        
        # Map SpaCy entity types to our node types
        entity_type_mapping = {
            "PERSON": "Person",
            "ORG": "Project",
            "PRODUCT": "Project",
            "EVENT": "Problem",
            "WORK_OF_ART": "Document",
            "LAW": "Concept",
            "LANGUAGE": "Concept",
            "NORP": "Concept",
            "FAC": "Project",
            "GPE": "Concept",
        }
        
        for ent in doc.ents:
            node_type = entity_type_mapping.get(ent.label_, "Concept")
            
            entity = {
                "text": ent.text,
                "type": node_type,
                "label": ent.label_,
                "start": ent.start_char,
                "end": ent.end_char
            }
            entities.append(entity)
        
        # Extract noun chunks as potential concepts
        for chunk in doc.noun_chunks:
            # Filter out common words and short chunks
            if len(chunk.text.split()) >= 2 and chunk.root.pos_ in ["NOUN", "PROPN"]:
                # Check if already captured as named entity
                overlap = False
                for ent in entities:
                    if (chunk.start_char >= ent["start"] and chunk.end_char <= ent["end"]):
                        overlap = True
                        break
                
                if not overlap:
                    entities.append({
                        "text": chunk.text,
                        "type": "Concept",
                        "label": "NOUN_CHUNK",
                        "start": chunk.start_char,
                        "end": chunk.end_char
                    })
        
        # Deduplicate by normalized text
        seen = set()
        unique_entities = []
        for entity in entities:
            normalized = entity["text"].lower().strip()
            if normalized not in seen and len(normalized) > 2:
                seen.add(normalized)
                unique_entities.append(entity)
        
        logger.info(f"Extracted {len(unique_entities)} entities from text")
        return unique_entities
    
    def extract_relations_cooccurrence(
        self,
        entities: List[Dict[str, Any]],
        text: str
    ) -> List[Dict[str, Any]]:
        """
        Extract relations based on co-occurrence within sentence windows.
        
        Args:
            entities: List of extracted entities
            text: Original text
        
        Returns:
            List of relations with source, target, and type
        """
        # Split text into sentences
        doc = self.nlp(text)
        sentences = list(doc.sents)
        
        # Map entities to sentences
        entity_to_sentences = defaultdict(list)
        for entity in entities:
            for sent_idx, sent in enumerate(sentences):
                if (entity["start"] >= sent.start_char and 
                    entity["end"] <= sent.end_char):
                    entity_to_sentences[entity["text"]].append(sent_idx)
        
        relations = []
        
        # Find co-occurring entities within window
        for i, entity1 in enumerate(entities):
            for entity2 in entities[i+1:]:
                if entity1["text"] == entity2["text"]:
                    continue
                
                sents1 = entity_to_sentences[entity1["text"]]
                sents2 = entity_to_sentences[entity2["text"]]
                
                # Check if entities co-occur within window
                for s1 in sents1:
                    for s2 in sents2:
                        if abs(s1 - s2) <= self.COOCCURRENCE_WINDOW:
                            # Determine relation type based on entity types
                            rel_type = self._infer_relation_type(
                                entity1["type"],
                                entity2["type"]
                            )
                            
                            relations.append({
                                "source": entity1["text"],
                                "source_type": entity1["type"],
                                "target": entity2["text"],
                                "target_type": entity2["type"],
                                "type": rel_type,
                                "method": "co-occurrence",
                                "confidence": 0.6
                            })
                            break
                    else:
                        continue
                    break
        
        logger.info(f"Extracted {len(relations)} co-occurrence relations")
        return relations
    
    def extract_relations_explicit(
        self,
        entities: List[Dict[str, Any]],
        text: str
    ) -> List[Dict[str, Any]]:
        """
        Extract explicit relations using pattern matching.
        
        Args:
            entities: List of extracted entities
            text: Original text
        
        Returns:
            List of explicit relations
        """
        doc = self.nlp(text)
        relations = []
        
        # Relation patterns
        patterns = {
            "WORKS_ON": [
                r"{} (?:works? on|developed?|created?|built?|designed?) {}",
                r"{} (?:is|was) (?:working on|developing|creating|building) {}",
            ],
            "CAUSED_BY": [
                r"{} (?:caused? by|due to|resulted? from|stemmed? from) {}",
                r"{} (?:is|was) (?:caused by|due to) {}",
            ],
            "SOLVED_BY": [
                r"{} (?:solved? by|fixed by|resolved? by|addressed? by) {}",
                r"{} (?:is|was) (?:solved|fixed|resolved) by {}",
            ],
            "LEARNED_FROM": [
                r"{} (?:learned? from|derived from|based on) {}",
                r"(?:lesson|insight|takeaway) from {}.*?{}",
            ]
        }
        
        # Check patterns between entity pairs
        text_lower = text.lower()
        for entity1 in entities:
            for entity2 in entities:
                if entity1["text"] == entity2["text"]:
                    continue
                
                e1_text = re.escape(entity1["text"].lower())
                e2_text = re.escape(entity2["text"].lower())
                
                for rel_type, pattern_list in patterns.items():
                    for pattern_template in pattern_list:
                        pattern = pattern_template.format(e1_text, e2_text)
                        if re.search(pattern, text_lower, re.IGNORECASE):
                            relations.append({
                                "source": entity1["text"],
                                "source_type": entity1["type"],
                                "target": entity2["text"],
                                "target_type": entity2["type"],
                                "type": rel_type,
                                "method": "explicit",
                                "confidence": 0.9
                            })
                            break
        
        logger.info(f"Extracted {len(relations)} explicit relations")
        return relations
    
    def _infer_relation_type(self, source_type: str, target_type: str) -> str:
        """Infer relation type based on node types."""
        # Person -> Project: WORKS_ON
        if source_type == "Person" and target_type == "Project":
            return "WORKS_ON"
        
        # Problem -> Person/Concept: SOLVED_BY
        if source_type == "Problem" and target_type in ["Person", "Concept"]:
            return "SOLVED_BY"
        
        # Problem -> Concept/Action: CAUSED_BY
        if source_type == "Problem" and target_type == "Concept":
            return "CAUSED_BY"
        
        # Lesson -> Problem/Project: LEARNED_FROM
        if source_type == "Lesson" and target_type in ["Problem", "Project"]:
            return "LEARNED_FROM"
        
        # Default: RELATES_TO
        return "RELATES_TO"
    
    def add_entities_to_graph(
        self,
        entities: List[Dict[str, Any]],
        document_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Add extracted entities to Neo4j graph.
        
        Args:
            entities: List of entities to add
            document_id: Optional document ID for provenance
        
        Returns:
            Statistics about added entities
        """
        with self.driver.session() as session:
            added = 0
            for entity in entities:
                try:
                    # Generate embedding
                    embedding = self.embedding_model.encode(entity["text"]).tolist()
                    
                    # Create or update node
                    query = f"""
                    MERGE (n:{entity['type']} {{name: $name}})
                    ON CREATE SET 
                        n.created_at = datetime(),
                        n.embedding = $embedding,
                        n.entity_label = $label,
                        n.source_document = $doc_id
                    ON MATCH SET 
                        n.updated_at = datetime(),
                        n.embedding = $embedding
                    RETURN n
                    """
                    
                    session.run(
                        query,
                        name=entity["text"],
                        embedding=embedding,
                        label=entity["label"],
                        doc_id=document_id
                    )
                    added += 1
                    
                except Neo4jError as e:
                    logger.error(f"Error adding entity {entity['text']}: {e}")
        
        logger.info(f"Added {added} entities to graph")
        return {
            "entities_added": added,
            "total_entities": len(entities)
        }
    
    def add_relations_to_graph(
        self,
        relations: List[Dict[str, Any]],
        document_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Add extracted relations to Neo4j graph.
        
        Args:
            relations: List of relations to add
            document_id: Optional document ID for provenance
        
        Returns:
            Statistics about added relations
        """
        with self.driver.session() as session:
            added = 0
            for rel in relations:
                try:
                    query = f"""
                    MATCH (source:{rel['source_type']} {{name: $source_name}})
                    MATCH (target:{rel['target_type']} {{name: $target_name}})
                    MERGE (source)-[r:{rel['type']}]->(target)
                    ON CREATE SET 
                        r.created_at = datetime(),
                        r.method = $method,
                        r.confidence = $confidence,
                        r.source_document = $doc_id
                    ON MATCH SET 
                        r.updated_at = datetime(),
                        r.confidence = CASE 
                            WHEN $confidence > r.confidence THEN $confidence 
                            ELSE r.confidence 
                        END
                    RETURN r
                    """
                    
                    session.run(
                        query,
                        source_name=rel["source"],
                        target_name=rel["target"],
                        method=rel["method"],
                        confidence=rel["confidence"],
                        doc_id=document_id
                    )
                    added += 1
                    
                except Neo4jError as e:
                    logger.error(f"Error adding relation {rel['source']}->{rel['target']}: {e}")
        
        logger.info(f"Added {added} relations to graph")
        return {
            "relations_added": added,
            "total_relations": len(relations)
        }
    
    def process_document(
        self,
        text: str,
        document_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Process a document: extract entities and relations, add to graph.
        
        Args:
            text: Document text
            document_id: Optional document ID
            metadata: Optional metadata
        
        Returns:
            Processing results with statistics
        """
        logger.info(f"Processing document: {document_id}")
        
        # Extract entities
        entities = self.extract_entities(text)
        
        # Extract relations (both methods)
        relations_cooccur = self.extract_relations_cooccurrence(entities, text)
        relations_explicit = self.extract_relations_explicit(entities, text)
        
        # Combine relations and deduplicate
        all_relations = relations_cooccur + relations_explicit
        unique_relations = []
        seen_pairs = set()
        
        for rel in all_relations:
            pair_key = (rel["source"], rel["target"], rel["type"])
            if pair_key not in seen_pairs:
                seen_pairs.add(pair_key)
                unique_relations.append(rel)
        
        # Add to graph
        entity_stats = self.add_entities_to_graph(entities, document_id)
        relation_stats = self.add_relations_to_graph(unique_relations, document_id)
        
        # Add document node if metadata provided
        if metadata:
            self._add_document_node(document_id, metadata, entities)
        
        result = {
            "status": "success",
            "document_id": document_id,
            "entities_extracted": len(entities),
            "entities_added": entity_stats["entities_added"],
            "relations_extracted": len(unique_relations),
            "relations_added": relation_stats["relations_added"],
            "relations_by_method": {
                "co-occurrence": len(relations_cooccur),
                "explicit": len(relations_explicit)
            }
        }
        
        logger.info(f"Document processing complete: {result}")
        return result
    
    def _add_document_node(
        self,
        document_id: str,
        metadata: Dict[str, Any],
        entities: List[Dict[str, Any]]
    ):
        """Add a Document node and link to extracted entities."""
        with self.driver.session() as session:
            # Create document node
            query = """
            MERGE (d:Document {name: $doc_id})
            SET d.title = $title,
                d.created_at = datetime(),
                d.metadata = $metadata
            RETURN d
            """
            session.run(
                query,
                doc_id=document_id,
                title=metadata.get("title", document_id),
                metadata=metadata
            )
            
            # Link document to entities
            for entity in entities:
                link_query = f"""
                MATCH (d:Document {{name: $doc_id}})
                MATCH (e:{entity['type']} {{name: $entity_name}})
                MERGE (d)-[r:MENTIONS]->(e)
                SET r.created_at = datetime()
                """
                try:
                    session.run(
                        link_query,
                        doc_id=document_id,
                        entity_name=entity["text"]
                    )
                except Neo4jError as e:
                    logger.debug(f"Error linking document to entity: {e}")
    
    def query_graph(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Execute a Cypher query on the graph.
        
        Args:
            query: Cypher query string
            parameters: Query parameters
        
        Returns:
            Query results as list of dictionaries
        """
        with self.driver.session() as session:
            try:
                result = session.run(query, parameters or {})
                records = [dict(record) for record in result]
                logger.info(f"Query returned {len(records)} records")
                return records
            except Neo4jError as e:
                logger.error(f"Query error: {e}")
                raise
    
    def get_neighbors(
        self,
        entity_name: str,
        entity_type: Optional[str] = None,
        relation_types: Optional[List[str]] = None,
        max_depth: int = 1,
        limit: int = 50
    ) -> Dict[str, Any]:
        """
        Get neighbors of an entity in the graph.
        
        Args:
            entity_name: Name of the entity
            entity_type: Optional type filter
            relation_types: Optional relation type filters
            max_depth: Maximum traversal depth
            limit: Maximum number of neighbors
        
        Returns:
            Dictionary with entity, neighbors, and relationships
        """
        # Build query based on parameters
        if entity_type:
            match_clause = f"MATCH (e:{entity_type} {{name: $name}})"
        else:
            # Match any node type
            type_union = "|".join(self.NODE_TYPES)
            match_clause = f"MATCH (e:{type_union} {{name: $name}})"
        
        if relation_types:
            rel_filter = "|".join(relation_types)
            path_clause = f"-[r:{rel_filter}*1..{max_depth}]-"
        else:
            path_clause = f"-[r*1..{max_depth}]-"
        
        query = f"""
        {match_clause}
        MATCH path = (e){path_clause}(neighbor)
        WHERE e <> neighbor
        RETURN DISTINCT 
            neighbor.name as name,
            labels(neighbor)[0] as type,
            [rel in relationships(path) | type(rel)] as rel_types,
            length(path) as distance
        ORDER BY distance ASC
        LIMIT $limit
        """
        
        with self.driver.session() as session:
            try:
                result = session.run(
                    query,
                    name=entity_name,
                    limit=limit
                )
                
                neighbors = []
                for record in result:
                    neighbors.append({
                        "name": record["name"],
                        "type": record["type"],
                        "relation_types": record["rel_types"],
                        "distance": record["distance"]
                    })
                
                return {
                    "entity": entity_name,
                    "entity_type": entity_type,
                    "neighbors_count": len(neighbors),
                    "neighbors": neighbors
                }
                
            except Neo4jError as e:
                logger.error(f"Error getting neighbors: {e}")
                raise
    
    def search_entities(
        self,
        search_text: str,
        entity_types: Optional[List[str]] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Search entities using full-text search.
        
        Args:
            search_text: Search query
            entity_types: Optional entity type filters
            limit: Maximum results
        
        Returns:
            List of matching entities
        """
        with self.driver.session() as session:
            try:
                # Use full-text search
                query = """
                CALL db.index.fulltext.queryNodes('entity_search', $search_text)
                YIELD node, score
                WHERE $types IS NULL OR ANY(label IN labels(node) WHERE label IN $types)
                RETURN 
                    node.name as name,
                    labels(node)[0] as type,
                    score,
                    node.created_at as created_at,
                    node.entity_label as entity_label
                ORDER BY score DESC
                LIMIT $limit
                """
                
                result = session.run(
                    query,
                    search_text=search_text,
                    types=entity_types,
                    limit=limit
                )
                
                entities = []
                for record in result:
                    entities.append({
                        "name": record["name"],
                        "type": record["type"],
                        "score": record["score"],
                        "created_at": str(record["created_at"]) if record["created_at"] else None,
                        "entity_label": record["entity_label"]
                    })
                
                return entities
                
            except Neo4jError as e:
                logger.error(f"Error searching entities: {e}")
                raise
    
    def get_graph_stats(self) -> Dict[str, Any]:
        """Get graph statistics."""
        with self.driver.session() as session:
            # Count nodes by type
            node_counts = {}
            for node_type in self.NODE_TYPES:
                result = session.run(f"MATCH (n:{node_type}) RETURN count(n) as count")
                node_counts[node_type] = result.single()["count"]
            
            # Count relationships by type
            rel_counts = {}
            for rel_type in self.RELATION_TYPES:
                result = session.run(f"MATCH ()-[r:{rel_type}]->() RETURN count(r) as count")
                rel_counts[rel_type] = result.single()["count"]
            
            # Get total counts
            total_nodes = session.run("MATCH (n) RETURN count(n) as count").single()["count"]
            total_rels = session.run("MATCH ()-[r]->() RETURN count(r) as count").single()["count"]
            
            return {
                "total_nodes": total_nodes,
                "total_relationships": total_rels,
                "nodes_by_type": node_counts,
                "relationships_by_type": rel_counts
            }
    
    def close(self):
        """Close Neo4j driver."""
        if self.driver:
            self.driver.close()
            logger.info("Neo4j driver closed")
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

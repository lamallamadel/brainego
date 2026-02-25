#!/usr/bin/env python3
"""
Data Integrity Validation Script
Validates data consistency across Qdrant, Neo4j, and PostgreSQL after restore
"""

import os
import sys
import logging
import hashlib
from typing import Dict, List, Tuple
from datetime import datetime

import httpx
import psycopg2
from neo4j import GraphDatabase
from qdrant_client import QdrantClient


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DataIntegrityValidator:
    """Validates data integrity across all databases"""
    
    def __init__(self):
        # Qdrant configuration
        self.qdrant_host = os.getenv('QDRANT_HOST', 'qdrant')
        self.qdrant_port = int(os.getenv('QDRANT_PORT', '6333'))
        
        # Neo4j configuration
        self.neo4j_uri = os.getenv('NEO4J_URI', 'bolt://neo4j:7687')
        self.neo4j_user = os.getenv('NEO4J_USER', 'neo4j')
        self.neo4j_password = os.getenv('NEO4J_PASSWORD', 'neo4j_password')
        
        # PostgreSQL configuration
        self.postgres_host = os.getenv('POSTGRES_HOST', 'postgres')
        self.postgres_port = int(os.getenv('POSTGRES_PORT', '5432'))
        self.postgres_db = os.getenv('POSTGRES_DB', 'ai_platform')
        self.postgres_user = os.getenv('POSTGRES_USER', 'ai_user')
        self.postgres_password = os.getenv('POSTGRES_PASSWORD', 'ai_password')
        
        self.validation_results = {
            'qdrant': {},
            'neo4j': {},
            'postgres': {},
            'cross_validation': {}
        }
    
    def validate_qdrant(self) -> Dict:
        """Validate Qdrant vector database"""
        logger.info("Validating Qdrant...")
        
        results = {
            'status': 'unknown',
            'health': False,
            'collections': [],
            'total_vectors': 0,
            'issues': []
        }
        
        try:
            client = QdrantClient(host=self.qdrant_host, port=self.qdrant_port)
            
            # Check health
            try:
                collections = client.get_collections()
                results['health'] = True
            except Exception as e:
                results['issues'].append(f"Health check failed: {str(e)}")
                results['status'] = 'failed'
                return results
            
            # List collections
            for collection in collections.collections:
                collection_info = client.get_collection(collection.name)
                
                vector_count = collection_info.points_count
                results['collections'].append({
                    'name': collection.name,
                    'vector_count': vector_count,
                    'vector_size': collection_info.config.params.vectors.size
                })
                results['total_vectors'] += vector_count
            
            # Basic integrity checks
            if results['total_vectors'] == 0:
                results['issues'].append("No vectors found in any collection")
            
            # Check for empty collections
            empty_collections = [
                c['name'] for c in results['collections'] 
                if c['vector_count'] == 0
            ]
            if empty_collections:
                results['issues'].append(
                    f"Empty collections found: {', '.join(empty_collections)}"
                )
            
            results['status'] = 'passed' if not results['issues'] else 'warning'
            
        except Exception as e:
            results['status'] = 'failed'
            results['issues'].append(f"Validation error: {str(e)}")
        
        return results
    
    def validate_neo4j(self) -> Dict:
        """Validate Neo4j graph database"""
        logger.info("Validating Neo4j...")
        
        results = {
            'status': 'unknown',
            'health': False,
            'node_count': 0,
            'relationship_count': 0,
            'node_labels': [],
            'relationship_types': [],
            'issues': []
        }
        
        try:
            driver = GraphDatabase.driver(
                self.neo4j_uri,
                auth=(self.neo4j_user, self.neo4j_password)
            )
            
            with driver.session() as session:
                # Check health
                try:
                    session.run("RETURN 1")
                    results['health'] = True
                except Exception as e:
                    results['issues'].append(f"Health check failed: {str(e)}")
                    results['status'] = 'failed'
                    return results
                
                # Count nodes
                result = session.run("MATCH (n) RETURN count(n) as count")
                results['node_count'] = result.single()['count']
                
                # Count relationships
                result = session.run("MATCH ()-[r]->() RETURN count(r) as count")
                results['relationship_count'] = result.single()['count']
                
                # Get node labels
                result = session.run("CALL db.labels()")
                results['node_labels'] = [record['label'] for record in result]
                
                # Get relationship types
                result = session.run("CALL db.relationshipTypes()")
                results['relationship_types'] = [record['relationshipType'] for record in result]
                
                # Check for orphaned nodes
                result = session.run(
                    "MATCH (n) WHERE NOT (n)--() RETURN count(n) as count"
                )
                orphaned_count = result.single()['count']
                if orphaned_count > 0:
                    results['issues'].append(
                        f"{orphaned_count} orphaned nodes found (no relationships)"
                    )
                
                # Check for duplicate relationships
                result = session.run("""
                    MATCH (a)-[r]->(b)
                    WITH a, b, type(r) as rel_type, count(*) as cnt
                    WHERE cnt > 1
                    RETURN count(*) as duplicates
                """)
                duplicate_count = result.single()['duplicates']
                if duplicate_count > 0:
                    results['issues'].append(
                        f"{duplicate_count} duplicate relationships found"
                    )
            
            driver.close()
            
            # Basic integrity checks
            if results['node_count'] == 0:
                results['issues'].append("No nodes found in graph database")
            
            if results['relationship_count'] == 0 and results['node_count'] > 0:
                results['issues'].append("Nodes exist but no relationships found")
            
            results['status'] = 'passed' if not results['issues'] else 'warning'
            
        except Exception as e:
            results['status'] = 'failed'
            results['issues'].append(f"Validation error: {str(e)}")
        
        return results
    
    def validate_postgresql(self) -> Dict:
        """Validate PostgreSQL database"""
        logger.info("Validating PostgreSQL...")
        
        results = {
            'status': 'unknown',
            'health': False,
            'tables': [],
            'total_rows': 0,
            'issues': []
        }
        
        try:
            conn = psycopg2.connect(
                host=self.postgres_host,
                port=self.postgres_port,
                database=self.postgres_db,
                user=self.postgres_user,
                password=self.postgres_password,
                connect_timeout=10
            )
            cursor = conn.cursor()
            
            results['health'] = True
            
            # Get all tables
            cursor.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                AND table_type = 'BASE TABLE'
            """)
            
            table_names = [row[0] for row in cursor.fetchall()]
            
            # Count rows in each table
            for table in table_names:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    row_count = cursor.fetchone()[0]
                    results['tables'].append({
                        'name': table,
                        'row_count': row_count
                    })
                    results['total_rows'] += row_count
                except Exception as e:
                    results['issues'].append(
                        f"Failed to count rows in {table}: {str(e)}"
                    )
            
            # Check for expected tables
            expected_tables = [
                'feedback',
                'lora_adapters',
                'drift_metrics',
                'backup_history'
            ]
            
            missing_tables = [
                t for t in expected_tables 
                if t not in table_names
            ]
            
            if missing_tables:
                results['issues'].append(
                    f"Expected tables missing: {', '.join(missing_tables)}"
                )
            
            # Check for NULL values in critical columns
            if 'feedback' in table_names:
                cursor.execute("""
                    SELECT COUNT(*) FROM feedback 
                    WHERE query IS NULL OR response IS NULL
                """)
                null_count = cursor.fetchone()[0]
                if null_count > 0:
                    results['issues'].append(
                        f"{null_count} feedback records with NULL query/response"
                    )
            
            # Check for orphaned records (if applicable)
            if 'lora_adapters' in table_names:
                cursor.execute("""
                    SELECT COUNT(*) FROM lora_adapters 
                    WHERE status = 'active' AND s3_path IS NULL
                """)
                orphaned = cursor.fetchone()[0]
                if orphaned > 0:
                    results['issues'].append(
                        f"{orphaned} active LoRA adapters without S3 path"
                    )
            
            cursor.close()
            conn.close()
            
            # Basic integrity checks
            if results['total_rows'] == 0:
                results['issues'].append("No data found in any table")
            
            results['status'] = 'passed' if not results['issues'] else 'warning'
            
        except Exception as e:
            results['status'] = 'failed'
            results['issues'].append(f"Validation error: {str(e)}")
        
        return results
    
    def validate_cross_database_consistency(self) -> Dict:
        """Validate consistency across databases"""
        logger.info("Validating cross-database consistency...")
        
        results = {
            'status': 'unknown',
            'checks': [],
            'issues': []
        }
        
        try:
            # Connect to all databases
            qdrant_client = QdrantClient(host=self.qdrant_host, port=self.qdrant_port)
            neo4j_driver = GraphDatabase.driver(
                self.neo4j_uri,
                auth=(self.neo4j_user, self.neo4j_password)
            )
            pg_conn = psycopg2.connect(
                host=self.postgres_host,
                port=self.postgres_port,
                database=self.postgres_db,
                user=self.postgres_user,
                password=self.postgres_password
            )
            pg_cursor = pg_conn.cursor()
            
            # Check 1: Feedback count consistency
            pg_cursor.execute("SELECT COUNT(*) FROM feedback WHERE id IS NOT NULL")
            pg_feedback_count = pg_cursor.fetchone()[0]
            
            results['checks'].append({
                'name': 'feedback_count',
                'postgres_count': pg_feedback_count,
                'status': 'checked'
            })
            
            # Check 2: LoRA adapter references
            pg_cursor.execute("SELECT COUNT(*) FROM lora_adapters WHERE status = 'active'")
            active_adapters = pg_cursor.fetchone()[0]
            
            results['checks'].append({
                'name': 'active_lora_adapters',
                'count': active_adapters,
                'status': 'checked'
            })
            
            # Check 3: Vector collection alignment
            try:
                collections = qdrant_client.get_collections()
                collection_names = [c.name for c in collections.collections]
                
                expected_collections = ['documents']
                missing = [c for c in expected_collections if c not in collection_names]
                
                if missing:
                    results['issues'].append(
                        f"Expected Qdrant collections missing: {', '.join(missing)}"
                    )
                
                results['checks'].append({
                    'name': 'qdrant_collections',
                    'found': collection_names,
                    'expected': expected_collections,
                    'status': 'passed' if not missing else 'failed'
                })
            except Exception as e:
                results['issues'].append(f"Qdrant collection check failed: {e}")
            
            # Check 4: Neo4j graph structure
            with neo4j_driver.session() as session:
                # Check for expected node labels
                result = session.run("CALL db.labels()")
                labels = [record['label'] for record in result]
                
                results['checks'].append({
                    'name': 'neo4j_labels',
                    'found': labels,
                    'status': 'checked'
                })
            
            # Cleanup
            pg_cursor.close()
            pg_conn.close()
            neo4j_driver.close()
            
            results['status'] = 'passed' if not results['issues'] else 'warning'
            
        except Exception as e:
            results['status'] = 'failed'
            results['issues'].append(f"Cross-validation error: {str(e)}")
        
        return results
    
    def run_full_validation(self) -> Dict:
        """Run complete validation suite"""
        logger.info("=" * 80)
        logger.info("Starting Full Data Integrity Validation")
        logger.info("=" * 80)
        
        # Validate Qdrant
        self.validation_results['qdrant'] = self.validate_qdrant()
        
        # Validate Neo4j
        self.validation_results['neo4j'] = self.validate_neo4j()
        
        # Validate PostgreSQL
        self.validation_results['postgres'] = self.validate_postgresql()
        
        # Cross-database validation
        self.validation_results['cross_validation'] = self.validate_cross_database_consistency()
        
        return self.validation_results
    
    def generate_report(self) -> str:
        """Generate human-readable validation report"""
        report_lines = []
        report_lines.append("=" * 80)
        report_lines.append("DATA INTEGRITY VALIDATION REPORT")
        report_lines.append(f"Generated: {datetime.utcnow().isoformat()}")
        report_lines.append("=" * 80)
        report_lines.append("")
        
        # Qdrant section
        qdrant = self.validation_results['qdrant']
        report_lines.append("QDRANT VECTOR DATABASE")
        report_lines.append("-" * 40)
        report_lines.append(f"Status: {qdrant.get('status', 'unknown').upper()}")
        report_lines.append(f"Health: {'✓' if qdrant.get('health') else '✗'}")
        report_lines.append(f"Total Vectors: {qdrant.get('total_vectors', 0):,}")
        report_lines.append(f"Collections: {len(qdrant.get('collections', []))}")
        
        for collection in qdrant.get('collections', []):
            report_lines.append(
                f"  - {collection['name']}: {collection['vector_count']:,} vectors"
            )
        
        if qdrant.get('issues'):
            report_lines.append("Issues:")
            for issue in qdrant['issues']:
                report_lines.append(f"  ⚠ {issue}")
        report_lines.append("")
        
        # Neo4j section
        neo4j = self.validation_results['neo4j']
        report_lines.append("NEO4J GRAPH DATABASE")
        report_lines.append("-" * 40)
        report_lines.append(f"Status: {neo4j.get('status', 'unknown').upper()}")
        report_lines.append(f"Health: {'✓' if neo4j.get('health') else '✗'}")
        report_lines.append(f"Nodes: {neo4j.get('node_count', 0):,}")
        report_lines.append(f"Relationships: {neo4j.get('relationship_count', 0):,}")
        report_lines.append(f"Node Labels: {len(neo4j.get('node_labels', []))}")
        report_lines.append(f"Relationship Types: {len(neo4j.get('relationship_types', []))}")
        
        if neo4j.get('issues'):
            report_lines.append("Issues:")
            for issue in neo4j['issues']:
                report_lines.append(f"  ⚠ {issue}")
        report_lines.append("")
        
        # PostgreSQL section
        postgres = self.validation_results['postgres']
        report_lines.append("POSTGRESQL DATABASE")
        report_lines.append("-" * 40)
        report_lines.append(f"Status: {postgres.get('status', 'unknown').upper()}")
        report_lines.append(f"Health: {'✓' if postgres.get('health') else '✗'}")
        report_lines.append(f"Total Rows: {postgres.get('total_rows', 0):,}")
        report_lines.append(f"Tables: {len(postgres.get('tables', []))}")
        
        for table in postgres.get('tables', []):
            report_lines.append(
                f"  - {table['name']}: {table['row_count']:,} rows"
            )
        
        if postgres.get('issues'):
            report_lines.append("Issues:")
            for issue in postgres['issues']:
                report_lines.append(f"  ⚠ {issue}")
        report_lines.append("")
        
        # Cross-validation section
        cross = self.validation_results['cross_validation']
        report_lines.append("CROSS-DATABASE CONSISTENCY")
        report_lines.append("-" * 40)
        report_lines.append(f"Status: {cross.get('status', 'unknown').upper()}")
        
        for check in cross.get('checks', []):
            report_lines.append(f"  {check['name']}: {check['status']}")
        
        if cross.get('issues'):
            report_lines.append("Issues:")
            for issue in cross['issues']:
                report_lines.append(f"  ⚠ {issue}")
        report_lines.append("")
        
        # Overall summary
        report_lines.append("=" * 80)
        report_lines.append("OVERALL SUMMARY")
        report_lines.append("=" * 80)
        
        all_statuses = [
            qdrant.get('status'),
            neo4j.get('status'),
            postgres.get('status'),
            cross.get('status')
        ]
        
        if all(s == 'passed' for s in all_statuses):
            report_lines.append("✓ ALL VALIDATIONS PASSED")
        elif any(s == 'failed' for s in all_statuses):
            report_lines.append("✗ VALIDATION FAILURES DETECTED")
        else:
            report_lines.append("⚠ VALIDATION COMPLETED WITH WARNINGS")
        
        report_lines.append("")
        
        return "\n".join(report_lines)


def main():
    """Main entry point"""
    validator = DataIntegrityValidator()
    
    try:
        # Run validation
        results = validator.run_full_validation()
        
        # Generate and display report
        report = validator.generate_report()
        print(report)
        
        # Save report to file
        report_file = f"validation_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(report_file, 'w') as f:
            f.write(report)
        
        logger.info(f"Report saved to {report_file}")
        
        # Exit code based on results
        all_statuses = [
            results['qdrant'].get('status'),
            results['neo4j'].get('status'),
            results['postgres'].get('status'),
            results['cross_validation'].get('status')
        ]
        
        if any(s == 'failed' for s in all_statuses):
            sys.exit(1)
        else:
            sys.exit(0)
            
    except Exception as e:
        logger.error(f"Validation failed with exception: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()

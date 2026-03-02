#!/usr/bin/env python3
"""
Qdrant Collection Archival Service for Cost Optimization.

Moves embeddings older than 90 days from Qdrant to MinIO cold storage,
reducing active vector database size and costs while preserving data.
"""

import os
import sys
import logging
import json
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import gzip

# Needs: python-package:qdrant-client>=1.7.0
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, Range

# Needs: python-package:minio>=7.2.0
from minio import Minio
from minio.error import S3Error

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class QdrantArchivalService:
    """Service for archiving old Qdrant embeddings to MinIO cold storage."""

    def __init__(
        self,
        qdrant_host: str = "qdrant",
        qdrant_port: int = 6333,
        minio_endpoint: str = "minio:9000",
        minio_access_key: str = "",
        minio_secret_key: str = "",
        minio_bucket: str = "qdrant-archive",
        minio_secure: bool = False,
        archival_age_days: int = 90,
        batch_size: int = 1000,
        dry_run: bool = False
    ):
        """
        Initialize the archival service.

        Args:
            qdrant_host: Qdrant server hostname
            qdrant_port: Qdrant server port
            minio_endpoint: MinIO endpoint (host:port)
            minio_access_key: MinIO access key
            minio_secret_key: MinIO secret key
            minio_bucket: MinIO bucket for archives
            minio_secure: Use HTTPS for MinIO
            archival_age_days: Archive embeddings older than this many days
            batch_size: Number of points to process per batch
            dry_run: If True, simulate archival without deleting data
        """
        self.qdrant_client = QdrantClient(host=qdrant_host, port=qdrant_port)
        self.archival_age_days = archival_age_days
        self.batch_size = batch_size
        self.dry_run = dry_run
        
        # Initialize MinIO client
        self.minio_client = Minio(
            minio_endpoint,
            access_key=minio_access_key,
            secret_key=minio_secret_key,
            secure=minio_secure
        )
        self.minio_bucket = minio_bucket
        
        # Ensure bucket exists
        self._ensure_bucket()
        
        logger.info(f"Initialized Qdrant Archival Service")
        logger.info(f"  Qdrant: {qdrant_host}:{qdrant_port}")
        logger.info(f"  MinIO: {minio_endpoint}/{minio_bucket}")
        logger.info(f"  Archival age: {archival_age_days} days")
        logger.info(f"  Batch size: {batch_size}")
        logger.info(f"  Dry run: {dry_run}")

    def _ensure_bucket(self):
        """Ensure the MinIO bucket exists."""
        try:
            if not self.minio_client.bucket_exists(self.minio_bucket):
                self.minio_client.make_bucket(self.minio_bucket)
                logger.info(f"Created MinIO bucket: {self.minio_bucket}")
            else:
                logger.info(f"MinIO bucket exists: {self.minio_bucket}")
        except S3Error as e:
            logger.error(f"Failed to ensure bucket: {e}")
            raise

    def get_archivable_points(
        self,
        collection_name: str,
        workspace_id: Optional[str] = None
    ) -> List[str]:
        """
        Find point IDs eligible for archival based on age.

        Args:
            collection_name: Qdrant collection name
            workspace_id: Optional workspace filter

        Returns:
            List of point IDs eligible for archival
        """
        cutoff_date = datetime.utcnow() - timedelta(days=self.archival_age_days)
        cutoff_timestamp = cutoff_date.isoformat()
        
        logger.info(f"Finding points older than {cutoff_timestamp}")
        
        # Build filter
        filter_conditions = [
            FieldCondition(
                key="ingested_at",
                range=Range(lt=cutoff_timestamp)
            )
        ]
        
        if workspace_id:
            from qdrant_client.models import MatchValue
            filter_conditions.append(
                FieldCondition(
                    key="workspace_id",
                    match=MatchValue(value=workspace_id)
                )
            )
        
        query_filter = Filter(must=filter_conditions)
        
        # Scroll through all matching points
        archivable_ids = []
        offset = None
        
        while True:
            result = self.qdrant_client.scroll(
                collection_name=collection_name,
                scroll_filter=query_filter,
                limit=self.batch_size,
                offset=offset,
                with_payload=True,
                with_vectors=True
            )
            
            points, next_offset = result
            
            if not points:
                break
            
            archivable_ids.extend([str(point.id) for point in points])
            
            if next_offset is None:
                break
            
            offset = next_offset
        
        logger.info(f"Found {len(archivable_ids)} archivable points in collection '{collection_name}'")
        return archivable_ids

    def archive_points(
        self,
        collection_name: str,
        point_ids: List[str],
        workspace_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Archive points to MinIO and optionally delete from Qdrant.

        Args:
            collection_name: Qdrant collection name
            point_ids: List of point IDs to archive
            workspace_id: Optional workspace identifier for organization

        Returns:
            Archive operation statistics
        """
        if not point_ids:
            logger.info("No points to archive")
            return {
                "status": "success",
                "points_archived": 0,
                "points_deleted": 0,
                "archive_files": []
            }
        
        logger.info(f"Archiving {len(point_ids)} points from collection '{collection_name}'")
        
        archived_files = []
        archived_count = 0
        deleted_count = 0
        
        # Process in batches
        for i in range(0, len(point_ids), self.batch_size):
            batch_ids = point_ids[i:i + self.batch_size]
            batch_num = i // self.batch_size + 1
            
            logger.info(f"Processing batch {batch_num} ({len(batch_ids)} points)")
            
            # Retrieve points with vectors and payloads
            points = self.qdrant_client.retrieve(
                collection_name=collection_name,
                ids=batch_ids,
                with_payload=True,
                with_vectors=True
            )
            
            if not points:
                logger.warning(f"Batch {batch_num}: No points retrieved")
                continue
            
            # Prepare archive data
            archive_data = []
            for point in points:
                archive_data.append({
                    "id": str(point.id),
                    "vector": point.vector,
                    "payload": point.payload,
                    "archived_at": datetime.utcnow().isoformat()
                })
            
            # Create archive file name
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            workspace_prefix = f"{workspace_id}/" if workspace_id else ""
            archive_filename = f"{workspace_prefix}{collection_name}/archive_{timestamp}_batch_{batch_num}.json.gz"
            
            # Compress and upload to MinIO
            archive_json = json.dumps(archive_data, indent=2)
            compressed_data = gzip.compress(archive_json.encode('utf-8'))
            
            if not self.dry_run:
                try:
                    from io import BytesIO
                    
                    self.minio_client.put_object(
                        self.minio_bucket,
                        archive_filename,
                        BytesIO(compressed_data),
                        length=len(compressed_data),
                        content_type="application/gzip"
                    )
                    
                    logger.info(f"Uploaded archive: {archive_filename} ({len(compressed_data)} bytes)")
                    archived_files.append(archive_filename)
                    archived_count += len(archive_data)
                    
                    # Delete from Qdrant
                    self.qdrant_client.delete(
                        collection_name=collection_name,
                        points_selector=batch_ids
                    )
                    
                    deleted_count += len(batch_ids)
                    logger.info(f"Deleted {len(batch_ids)} points from Qdrant")
                    
                except Exception as e:
                    logger.error(f"Failed to archive batch {batch_num}: {e}")
                    continue
            else:
                logger.info(f"[DRY RUN] Would upload: {archive_filename} ({len(compressed_data)} bytes)")
                logger.info(f"[DRY RUN] Would delete {len(batch_ids)} points from Qdrant")
                archived_files.append(archive_filename)
                archived_count += len(archive_data)
        
        result = {
            "status": "success",
            "collection": collection_name,
            "workspace_id": workspace_id,
            "points_archived": archived_count,
            "points_deleted": deleted_count if not self.dry_run else 0,
            "archive_files": archived_files,
            "dry_run": self.dry_run
        }
        
        logger.info(f"Archive complete: {archived_count} points archived, {deleted_count} deleted")
        return result

    def archive_collection(
        self,
        collection_name: str,
        workspace_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Archive old points from a collection.

        Args:
            collection_name: Qdrant collection name
            workspace_id: Optional workspace filter

        Returns:
            Archive operation statistics
        """
        logger.info(f"Starting archival for collection '{collection_name}'")
        
        # Find archivable points
        point_ids = self.get_archivable_points(collection_name, workspace_id)
        
        if not point_ids:
            logger.info("No points eligible for archival")
            return {
                "status": "success",
                "collection": collection_name,
                "workspace_id": workspace_id,
                "points_archived": 0,
                "points_deleted": 0,
                "archive_files": []
            }
        
        # Archive points
        result = self.archive_points(collection_name, point_ids, workspace_id)
        
        return result

    def list_archives(
        self,
        collection_name: Optional[str] = None,
        workspace_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List archived files in MinIO.

        Args:
            collection_name: Optional collection filter
            workspace_id: Optional workspace filter

        Returns:
            List of archive file metadata
        """
        prefix = ""
        if workspace_id:
            prefix = f"{workspace_id}/"
        if collection_name:
            prefix += f"{collection_name}/"
        
        objects = self.minio_client.list_objects(
            self.minio_bucket,
            prefix=prefix if prefix else None,
            recursive=True
        )
        
        archives = []
        for obj in objects:
            archives.append({
                "filename": obj.object_name,
                "size_bytes": obj.size,
                "size_mb": round(obj.size / (1024 * 1024), 2),
                "last_modified": obj.last_modified.isoformat() if obj.last_modified else None
            })
        
        return archives

    def restore_archive(
        self,
        archive_filename: str,
        collection_name: str
    ) -> Dict[str, Any]:
        """
        Restore archived points back to Qdrant.

        Args:
            archive_filename: Archive file name in MinIO
            collection_name: Target Qdrant collection

        Returns:
            Restore operation statistics
        """
        logger.info(f"Restoring archive: {archive_filename} to collection '{collection_name}'")
        
        try:
            # Download from MinIO
            response = self.minio_client.get_object(self.minio_bucket, archive_filename)
            compressed_data = response.read()
            response.close()
            response.release_conn()
            
            # Decompress
            decompressed_data = gzip.decompress(compressed_data)
            archive_data = json.loads(decompressed_data.decode('utf-8'))
            
            logger.info(f"Downloaded archive: {len(archive_data)} points")
            
            # Restore to Qdrant
            from qdrant_client.models import PointStruct
            
            points = []
            for item in archive_data:
                points.append(
                    PointStruct(
                        id=item["id"],
                        vector=item["vector"],
                        payload=item["payload"]
                    )
                )
            
            if not self.dry_run:
                self.qdrant_client.upsert(
                    collection_name=collection_name,
                    points=points
                )
                logger.info(f"Restored {len(points)} points to Qdrant")
            else:
                logger.info(f"[DRY RUN] Would restore {len(points)} points to Qdrant")
            
            return {
                "status": "success",
                "archive_file": archive_filename,
                "collection": collection_name,
                "points_restored": len(points),
                "dry_run": self.dry_run
            }
            
        except Exception as e:
            logger.error(f"Failed to restore archive: {e}")
            raise


def main():
    """Main entry point."""
    # Configuration from environment
    qdrant_host = os.getenv("QDRANT_HOST", "qdrant")
    qdrant_port = int(os.getenv("QDRANT_PORT", "6333"))
    minio_endpoint = os.getenv("MINIO_ENDPOINT", "minio:9000")
    minio_access_key = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    minio_secret_key = os.getenv("MINIO_SECRET_KEY", "minioadmin123")
    minio_bucket = os.getenv("MINIO_ARCHIVE_BUCKET", "qdrant-archive")
    archival_age_days = int(os.getenv("ARCHIVAL_AGE_DAYS", "90"))
    batch_size = int(os.getenv("BATCH_SIZE", "1000"))
    dry_run = os.getenv("DRY_RUN", "false").lower() == "true"
    
    collection_name = os.getenv("COLLECTION_NAME", "documents")
    workspace_id = os.getenv("WORKSPACE_ID", None)
    
    logger.info("=" * 80)
    logger.info("Qdrant Collection Archival Service")
    logger.info("=" * 80)
    
    try:
        # Initialize service
        service = QdrantArchivalService(
            qdrant_host=qdrant_host,
            qdrant_port=qdrant_port,
            minio_endpoint=minio_endpoint,
            minio_access_key=minio_access_key,
            minio_secret_key=minio_secret_key,
            minio_bucket=minio_bucket,
            archival_age_days=archival_age_days,
            batch_size=batch_size,
            dry_run=dry_run
        )
        
        # Run archival
        result = service.archive_collection(collection_name, workspace_id)
        
        logger.info("")
        logger.info("=" * 80)
        logger.info("ARCHIVAL SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Collection: {result['collection']}")
        if result.get('workspace_id'):
            logger.info(f"Workspace: {result['workspace_id']}")
        logger.info(f"Points archived: {result['points_archived']}")
        logger.info(f"Points deleted: {result['points_deleted']}")
        logger.info(f"Archive files: {len(result['archive_files'])}")
        logger.info("")
        
        if result['archive_files']:
            logger.info("Archive Files:")
            for filename in result['archive_files']:
                logger.info(f"  - {filename}")
        
        logger.info("=" * 80)
        
        return 0
        
    except Exception as e:
        logger.error(f"Archival failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())

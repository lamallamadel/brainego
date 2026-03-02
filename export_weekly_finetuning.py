#!/usr/bin/env python3
"""
Weekly Fine-tuning Dataset Export Script

Exports feedback data from the last 7 days with weighted samples:
- Positive feedback (thumbs-up): 2.0x weight
- Negative feedback (thumbs-down): 0.5x weight

Usage:
    python export_weekly_finetuning.py [output_path] [--days N]

Examples:
    python export_weekly_finetuning.py /tmp/dataset.jsonl
    python export_weekly_finetuning.py /tmp/dataset.jsonl --days 14
"""

import os
import sys
import argparse
import logging
from datetime import datetime, timedelta
from feedback_service import FeedbackService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def _env_flag(name: str, default: bool) -> bool:
    """Parse boolean flags from environment variables."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def main():
    parser = argparse.ArgumentParser(
        description="Export weekly fine-tuning dataset from feedback",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "output_path",
        nargs="?",
        default=None,
        help="Path to output JSONL file (default: auto-generated with timestamp)"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of days to look back (default: 7)"
    )
    parser.add_argument(
        "--db-host",
        default=os.getenv("POSTGRES_HOST", "localhost"),
        help="PostgreSQL host"
    )
    parser.add_argument(
        "--db-port",
        type=int,
        default=int(os.getenv("POSTGRES_PORT", "5432")),
        help="PostgreSQL port"
    )
    parser.add_argument(
        "--db-name",
        default=os.getenv("POSTGRES_DB", "ai_platform"),
        help="Database name"
    )
    parser.add_argument(
        "--db-user",
        default=os.getenv("POSTGRES_USER", "ai_user"),
        help="Database user"
    )
    parser.add_argument(
        "--db-password",
        default=os.getenv("POSTGRES_PASSWORD", "ai_password"),
        help="Database password"
    )
    parser.add_argument(
        "--format",
        default="jsonl",
        choices=["jsonl"],
        help="Export format (default: jsonl)"
    )
    parser.add_argument(
        "--min-query-chars",
        type=int,
        default=10,
        help="Minimum query length after normalization (default: 10)"
    )
    parser.add_argument(
        "--min-response-chars",
        type=int,
        default=20,
        help="Minimum response length after normalization (default: 20)"
    )
    parser.add_argument(
        "--no-deduplicate",
        action="store_true",
        help="Disable deduplication of query/response pairs"
    )
    parser.add_argument(
        "--minio-endpoint",
        default=os.getenv("MINIO_ENDPOINT", "minio:9000"),
        help="MinIO endpoint (host:port)"
    )
    parser.add_argument(
        "--minio-access-key",
        default=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
        help="MinIO access key"
    )
    parser.add_argument(
        "--minio-secret-key",
        default=os.getenv("MINIO_SECRET_KEY", "minioadmin123"),
        help="MinIO secret key"
    )
    parser.add_argument(
        "--minio-bucket",
        default=os.getenv("FINETUNING_DATASET_BUCKET", "finetuning-datasets"),
        help="MinIO bucket used to store exported JSONL files"
    )
    parser.add_argument(
        "--minio-prefix",
        default=os.getenv("FINETUNING_DATASET_PREFIX", "weekly"),
        help="MinIO object key prefix for exports"
    )
    parser.add_argument(
        "--minio-secure",
        dest="minio_secure",
        action="store_true",
        help="Use HTTPS to connect to MinIO"
    )
    parser.add_argument(
        "--minio-insecure",
        dest="minio_secure",
        action="store_false",
        help="Use HTTP to connect to MinIO"
    )
    parser.add_argument(
        "--upload-minio",
        dest="upload_minio",
        action="store_true",
        help="Upload exported dataset to MinIO (default)"
    )
    parser.add_argument(
        "--no-minio-upload",
        dest="upload_minio",
        action="store_false",
        help="Skip MinIO upload and only write local file"
    )
    parser.set_defaults(
        minio_secure=None,
        upload_minio=_env_flag("EXPORT_UPLOAD_TO_MINIO", True),
    )
    
    args = parser.parse_args()

    if args.minio_secure is None:
        args.minio_secure = _env_flag("MINIO_SECURE", False)
    
    # Generate output path if not provided
    if args.output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        args.output_path = f"finetuning_export_{timestamp}.jsonl"
    
    # Calculate date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=args.days)
    
    logger.info("=" * 60)
    logger.info("Weekly Fine-tuning Dataset Export")
    logger.info("=" * 60)
    logger.info(f"Database: {args.db_name}@{args.db_host}:{args.db_port}")
    logger.info(f"Date Range: {start_date.date()} to {end_date.date()} ({args.days} days)")
    logger.info(f"Output: {args.output_path}")
    logger.info(f"Format: {args.format}")
    logger.info(
        "Filters: min_query_chars=%s, min_response_chars=%s, deduplicate=%s",
        args.min_query_chars,
        args.min_response_chars,
        not args.no_deduplicate,
    )
    logger.info("Upload to MinIO: %s", args.upload_minio)
    if args.upload_minio:
        logger.info(
            "MinIO target: endpoint=%s bucket=%s prefix=%s secure=%s",
            args.minio_endpoint,
            args.minio_bucket,
            args.minio_prefix,
            args.minio_secure,
        )
    logger.info("=" * 60)
    
    try:
        # Initialize feedback service
        logger.info("Connecting to database...")
        service = FeedbackService(
            db_host=args.db_host,
            db_port=args.db_port,
            db_name=args.db_name,
            db_user=args.db_user,
            db_password=args.db_password
        )
        logger.info("✓ Connected to database")
        
        # Export dataset
        logger.info("Exporting dataset...")
        result = service.export_finetuning_dataset(
            output_path=args.output_path,
            start_date=start_date,
            end_date=end_date,
            format=args.format,
            min_query_chars=args.min_query_chars,
            min_response_chars=args.min_response_chars,
            deduplicate=not args.no_deduplicate,
            upload_to_minio=args.upload_minio,
            minio_bucket=args.minio_bucket,
            minio_prefix=args.minio_prefix,
            minio_endpoint=args.minio_endpoint,
            minio_access_key=args.minio_access_key,
            minio_secret_key=args.minio_secret_key,
            minio_secure=args.minio_secure,
        )
        
        logger.info("=" * 60)
        logger.info("Export Complete!")
        logger.info("=" * 60)
        logger.info(f"Status: {result['status']}")
        logger.info(f"Output File: {result['output_path']}")
        logger.info(f"Total Samples: {result['total_samples']}")
        logger.info(f"  - Positive (👍): {result['positive_samples']} samples (2.0x weight each)")
        logger.info(f"  - Negative (👎): {result['negative_samples']} samples (0.5x weight each)")
        logger.info(f"Total Weight: {result['total_weight']:.2f}")
        logger.info(f"Filtered Out: {result['filtered_out_samples']}")
        if result.get("minio_uri"):
            logger.info("MinIO URI: %s", result["minio_uri"])
        logger.info("=" * 60)
        
        # Calculate statistics
        if result['total_samples'] > 0:
            positive_pct = (result['positive_samples'] / result['total_samples']) * 100
            logger.info(f"Positive Percentage: {positive_pct:.2f}%")
            avg_weight = result['total_weight'] / result['total_samples']
            logger.info(f"Average Sample Weight: {avg_weight:.2f}x")
        
        # Close service
        service.close()
        logger.info("\n✓ Export completed successfully!")
        
        return 0
        
    except Exception as e:
        logger.error(f"✗ Export failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())

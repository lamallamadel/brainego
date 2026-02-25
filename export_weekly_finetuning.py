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
    
    args = parser.parse_args()
    
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
            format=args.format
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

"""
Data Loader for Training

Loads training data from feedback database and other sources.
"""

import logging
from typing import List, Dict
from datetime import datetime, timedelta
import json
import psycopg2
import os

logger = logging.getLogger(__name__)


def load_feedback_dataset(
    days: int = 7,
    db_host: str = None,
    db_port: int = None,
    db_name: str = None,
    db_user: str = None,
    db_password: str = None
) -> List[Dict[str, str]]:
    """
    Load training dataset from feedback database.
    
    Args:
        days: Number of days to look back
        db_host: Database host
        db_port: Database port
        db_name: Database name
        db_user: Database user
        db_password: Database password
    
    Returns:
        List of training samples with 'input' and 'output' keys
    """
    # Use environment variables as defaults
    db_host = db_host or os.getenv("POSTGRES_HOST", "localhost")
    db_port = db_port or int(os.getenv("POSTGRES_PORT", "5432"))
    db_name = db_name or os.getenv("POSTGRES_DB", "ai_platform")
    db_user = db_user or os.getenv("POSTGRES_USER", "ai_user")
    db_password = db_password or os.getenv("POSTGRES_PASSWORD", "ai_password")
    
    logger.info(f"Loading feedback data from {db_host}:{db_port}/{db_name}")
    
    conn = psycopg2.connect(
        host=db_host,
        port=db_port,
        dbname=db_name,
        user=db_user,
        password=db_password
    )
    
    cursor = conn.cursor()
    
    # Query feedback data
    query = """
    SELECT 
        request_data,
        response_data,
        feedback_type,
        created_at
    FROM feedback
    WHERE created_at >= NOW() - INTERVAL '%s days'
    AND feedback_type IN ('thumbs_up', 'thumbs_down')
    ORDER BY created_at DESC
    """
    
    cursor.execute(query, (days,))
    rows = cursor.fetchall()
    
    # Process samples
    samples = []
    for row in rows:
        request_data = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        response_data = json.loads(row[1]) if isinstance(row[1], str) else row[1]
        feedback_type = row[2]
        
        # Extract messages
        messages = request_data.get('messages', [])
        assistant_response = response_data.get('choices', [{}])[0].get('message', {}).get('content', '')
        
        # Format as training sample
        input_text = _format_messages(messages)
        output_text = assistant_response
        
        samples.append({
            'input': input_text,
            'output': output_text,
            'weight': 2.0 if feedback_type == 'thumbs_up' else 0.5,
            'feedback_type': feedback_type
        })
    
    cursor.close()
    conn.close()
    
    logger.info(f"✓ Loaded {len(samples)} samples")
    
    return samples


def _format_messages(messages: List[Dict]) -> str:
    """Format chat messages into a single string"""
    formatted = []
    for msg in messages:
        role = msg.get('role', 'user')
        content = msg.get('content', '')
        formatted.append(f"{role}: {content}")
    return "\n".join(formatted)


def load_dataset_from_file(file_path: str) -> List[Dict[str, str]]:
    """
    Load training dataset from JSONL file.
    
    Args:
        file_path: Path to JSONL file
    
    Returns:
        List of training samples
    """
    logger.info(f"Loading dataset from {file_path}")
    
    samples = []
    with open(file_path, 'r') as f:
        for line in f:
            data = json.loads(line)
            samples.append({
                'input': data.get('input', ''),
                'output': data.get('output', ''),
                'weight': data.get('weight', 1.0)
            })
    
    logger.info(f"✓ Loaded {len(samples)} samples from file")
    return samples

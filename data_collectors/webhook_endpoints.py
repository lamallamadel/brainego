#!/usr/bin/env python3
"""
Webhook Endpoints
Real-time ingestion endpoints for GitHub and Notion webhooks.
"""

import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime
import hmac
import hashlib

from fastapi import APIRouter, Request, HTTPException, Header
from pydantic import BaseModel

from data_collectors.ingestion_queue import IngestionQueue

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

ingestion_queue = IngestionQueue(
    redis_host=os.getenv("REDIS_HOST", "localhost"),
    redis_port=int(os.getenv("REDIS_PORT", "6379")),
    redis_db=int(os.getenv("REDIS_DB", "0"))
)


class WebhookPayload(BaseModel):
    """Generic webhook payload."""
    event: str
    data: Dict[str, Any]


def verify_github_signature(
    payload_body: bytes,
    signature_header: str,
    secret: str
) -> bool:
    """Verify GitHub webhook signature."""
    if not signature_header:
        return False
    
    hash_algorithm, github_signature = signature_header.split('=')
    
    expected_signature = hmac.new(
        secret.encode('utf-8'),
        payload_body,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected_signature, github_signature)


def verify_notion_signature(
    payload_body: bytes,
    signature_header: str,
    secret: str
) -> bool:
    """Verify Notion webhook signature."""
    if not signature_header:
        return False
    
    expected_signature = hmac.new(
        secret.encode('utf-8'),
        payload_body,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected_signature, signature_header)


@router.post("/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: Optional[str] = Header(None),
    x_github_event: Optional[str] = Header(None)
):
    """
    GitHub webhook endpoint.
    
    Handles events: issues, pull_request, push, issue_comment, etc.
    """
    body = await request.body()
    
    webhook_secret = os.getenv("GITHUB_WEBHOOK_SECRET")
    if webhook_secret:
        if not verify_github_signature(body, x_hub_signature_256 or "", webhook_secret):
            raise HTTPException(status_code=401, detail="Invalid signature")
    
    payload = await request.json()
    
    logger.info(f"Received GitHub webhook: {x_github_event}")
    
    try:
        document = _process_github_webhook(x_github_event, payload)
        
        if document:
            job_ids = ingestion_queue.enqueue_documents([document])
            
            return {
                "status": "success",
                "event": x_github_event,
                "job_ids": job_ids,
                "message": "Webhook processed and enqueued for ingestion"
            }
        else:
            return {
                "status": "ignored",
                "event": x_github_event,
                "message": "Event type not processed"
            }
    
    except Exception as e:
        logger.error(f"Error processing GitHub webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/notion")
async def notion_webhook(
    request: Request,
    notion_signature: Optional[str] = Header(None)
):
    """
    Notion webhook endpoint.
    
    Handles page and database update events.
    """
    body = await request.body()
    
    webhook_secret = os.getenv("NOTION_WEBHOOK_SECRET")
    if webhook_secret:
        if not verify_notion_signature(body, notion_signature or "", webhook_secret):
            raise HTTPException(status_code=401, detail="Invalid signature")
    
    payload = await request.json()
    
    logger.info(f"Received Notion webhook")
    
    try:
        document = _process_notion_webhook(payload)
        
        if document:
            job_ids = ingestion_queue.enqueue_documents([document])
            
            return {
                "status": "success",
                "job_ids": job_ids,
                "message": "Webhook processed and enqueued for ingestion"
            }
        else:
            return {
                "status": "ignored",
                "message": "Event type not processed"
            }
    
    except Exception as e:
        logger.error(f"Error processing Notion webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generic")
async def generic_webhook(payload: WebhookPayload):
    """
    Generic webhook endpoint for custom integrations.
    """
    logger.info(f"Received generic webhook: {payload.event}")
    
    try:
        document = {
            "text": str(payload.data),
            "metadata": {
                "source": "webhook",
                "type": payload.event,
                "collected_at": datetime.utcnow().isoformat(),
                "webhook_data": payload.data
            }
        }
        
        job_ids = ingestion_queue.enqueue_documents([document])
        
        return {
            "status": "success",
            "event": payload.event,
            "job_ids": job_ids,
            "message": "Webhook processed and enqueued for ingestion"
        }
    
    except Exception as e:
        logger.error(f"Error processing generic webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def webhook_status():
    """Get webhook endpoint status."""
    stats = ingestion_queue.get_queue_stats()
    
    return {
        "status": "active",
        "queue_stats": stats,
        "endpoints": {
            "github": "/webhooks/github",
            "notion": "/webhooks/notion",
            "generic": "/webhooks/generic"
        }
    }


def _process_github_webhook(
    event: str,
    payload: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """Process GitHub webhook payload into document."""
    
    if event == "issues":
        action = payload.get("action")
        issue = payload.get("issue", {})
        repo = payload.get("repository", {})
        
        if action in ["opened", "edited", "closed", "reopened"]:
            return {
                "text": f"# {issue.get('title', '')}\n\n{issue.get('body', '')}",
                "metadata": {
                    "source": "github",
                    "type": "issue",
                    "repository": repo.get("full_name", ""),
                    "issue_number": issue.get("number"),
                    "issue_url": issue.get("html_url", ""),
                    "state": issue.get("state", ""),
                    "action": action,
                    "author": issue.get("user", {}).get("login", ""),
                    "created_at": issue.get("created_at", ""),
                    "updated_at": issue.get("updated_at", ""),
                    "collected_at": datetime.utcnow().isoformat()
                }
            }
    
    elif event == "pull_request":
        action = payload.get("action")
        pr = payload.get("pull_request", {})
        repo = payload.get("repository", {})
        
        if action in ["opened", "edited", "closed", "reopened"]:
            return {
                "text": f"# {pr.get('title', '')}\n\n{pr.get('body', '')}",
                "metadata": {
                    "source": "github",
                    "type": "pull_request",
                    "repository": repo.get("full_name", ""),
                    "pr_number": pr.get("number"),
                    "pr_url": pr.get("html_url", ""),
                    "state": pr.get("state", ""),
                    "action": action,
                    "author": pr.get("user", {}).get("login", ""),
                    "created_at": pr.get("created_at", ""),
                    "updated_at": pr.get("updated_at", ""),
                    "collected_at": datetime.utcnow().isoformat()
                }
            }
    
    elif event == "issue_comment":
        action = payload.get("action")
        comment = payload.get("comment", {})
        issue = payload.get("issue", {})
        repo = payload.get("repository", {})
        
        if action in ["created", "edited"]:
            return {
                "text": f"# Comment on: {issue.get('title', '')}\n\n{comment.get('body', '')}",
                "metadata": {
                    "source": "github",
                    "type": "issue_comment",
                    "repository": repo.get("full_name", ""),
                    "issue_number": issue.get("number"),
                    "comment_url": comment.get("html_url", ""),
                    "action": action,
                    "author": comment.get("user", {}).get("login", ""),
                    "created_at": comment.get("created_at", ""),
                    "updated_at": comment.get("updated_at", ""),
                    "collected_at": datetime.utcnow().isoformat()
                }
            }
    
    elif event == "push":
        repo = payload.get("repository", {})
        commits = payload.get("commits", [])
        
        if commits:
            commit_texts = []
            for commit in commits:
                commit_texts.append(
                    f"- {commit.get('message', '')}\n  Author: {commit.get('author', {}).get('name', '')}"
                )
            
            return {
                "text": f"# Push to {repo.get('full_name', '')}\n\n" + "\n".join(commit_texts),
                "metadata": {
                    "source": "github",
                    "type": "push",
                    "repository": repo.get("full_name", ""),
                    "ref": payload.get("ref", ""),
                    "commits_count": len(commits),
                    "pusher": payload.get("pusher", {}).get("name", ""),
                    "collected_at": datetime.utcnow().isoformat()
                }
            }
    
    return None


def _process_notion_webhook(
    payload: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """Process Notion webhook payload into document."""
    
    event_type = payload.get("type")
    
    if event_type == "page":
        page = payload.get("page", {})
        
        return {
            "text": f"Notion page updated: {page.get('id', '')}",
            "metadata": {
                "source": "notion",
                "type": "page",
                "page_id": page.get("id", ""),
                "page_url": page.get("url", ""),
                "last_edited_time": page.get("last_edited_time", ""),
                "collected_at": datetime.utcnow().isoformat(),
                "webhook_event": True
            }
        }
    
    elif event_type == "database":
        database = payload.get("database", {})
        
        return {
            "text": f"Notion database updated: {database.get('id', '')}",
            "metadata": {
                "source": "notion",
                "type": "database",
                "database_id": database.get("id", ""),
                "last_edited_time": database.get("last_edited_time", ""),
                "collected_at": datetime.utcnow().isoformat(),
                "webhook_event": True
            }
        }
    
    return None

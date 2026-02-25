#!/usr/bin/env python3
"""
Notion Data Collector
Collects pages, databases, and blocks from Notion workspace.
"""

import os
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from notion_client import Client
from notion_client.errors import APIResponseError

logger = logging.getLogger(__name__)


class NotionCollector:
    """Collects data from Notion workspace."""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Notion collector.
        
        Args:
            api_key: Notion integration token
        """
        key = api_key or os.getenv("NOTION_API_KEY")
        if not key:
            raise ValueError("Notion API key is required")
        
        self.client = Client(auth=key)
        logger.info("Initialized Notion collector")
    
    def collect_recent_pages(
        self,
        hours_back: int = 4
    ) -> List[Dict[str, Any]]:
        """
        Collect recently updated pages.
        
        Args:
            hours_back: How many hours of history to collect
            
        Returns:
            List of collected documents
        """
        documents = []
        cutoff_time = datetime.utcnow() - timedelta(hours=hours_back)
        cutoff_iso = cutoff_time.isoformat() + "Z"
        
        try:
            response = self.client.search(
                filter={
                    "property": "object",
                    "value": "page"
                },
                sort={
                    "direction": "descending",
                    "timestamp": "last_edited_time"
                }
            )
            
            for page in response.get("results", []):
                last_edited = datetime.fromisoformat(
                    page["last_edited_time"].replace("Z", "+00:00")
                )
                
                if last_edited < cutoff_time:
                    continue
                
                page_content = self._get_page_content(page["id"])
                
                title = self._extract_title(page)
                
                text = f"# {title}\n\n{page_content}"
                
                documents.append({
                    "text": text,
                    "metadata": {
                        "source": "notion",
                        "type": "page",
                        "page_id": page["id"],
                        "page_url": page["url"],
                        "title": title,
                        "created_time": page["created_time"],
                        "last_edited_time": page["last_edited_time"],
                        "collected_at": datetime.utcnow().isoformat()
                    }
                })
            
            logger.info(f"Collected {len(documents)} Notion pages")
            
        except APIResponseError as e:
            logger.error(f"Error collecting Notion pages: {e}")
        
        return documents
    
    def collect_database_items(
        self,
        database_id: str,
        hours_back: int = 4
    ) -> List[Dict[str, Any]]:
        """
        Collect items from a Notion database.
        
        Args:
            database_id: Notion database ID
            hours_back: How many hours of history to collect
            
        Returns:
            List of collected documents
        """
        documents = []
        cutoff_time = datetime.utcnow() - timedelta(hours=hours_back)
        
        try:
            response = self.client.databases.query(
                database_id=database_id,
                sorts=[
                    {
                        "property": "last_edited_time",
                        "direction": "descending"
                    }
                ]
            )
            
            for page in response.get("results", []):
                last_edited = datetime.fromisoformat(
                    page["last_edited_time"].replace("Z", "+00:00")
                )
                
                if last_edited < cutoff_time:
                    continue
                
                page_content = self._get_page_content(page["id"])
                properties_text = self._format_properties(page.get("properties", {}))
                
                title = self._extract_title(page)
                
                text = f"# {title}\n\n## Properties\n\n{properties_text}\n\n## Content\n\n{page_content}"
                
                documents.append({
                    "text": text,
                    "metadata": {
                        "source": "notion",
                        "type": "database_item",
                        "database_id": database_id,
                        "page_id": page["id"],
                        "page_url": page["url"],
                        "title": title,
                        "created_time": page["created_time"],
                        "last_edited_time": page["last_edited_time"],
                        "collected_at": datetime.utcnow().isoformat()
                    }
                })
            
            logger.info(f"Collected {len(documents)} database items")
            
        except APIResponseError as e:
            logger.error(f"Error collecting database items: {e}")
        
        return documents
    
    def _get_page_content(self, page_id: str) -> str:
        """Extract text content from a Notion page."""
        try:
            blocks = self.client.blocks.children.list(block_id=page_id)
            content_parts = []
            
            for block in blocks.get("results", []):
                text = self._extract_block_text(block)
                if text:
                    content_parts.append(text)
            
            return "\n\n".join(content_parts)
            
        except Exception as e:
            logger.warning(f"Error getting page content for {page_id}: {e}")
            return ""
    
    def _extract_block_text(self, block: Dict[str, Any]) -> str:
        """Extract text from a Notion block."""
        block_type = block.get("type")
        
        if not block_type:
            return ""
        
        block_data = block.get(block_type, {})
        
        if "rich_text" in block_data:
            rich_text = block_data["rich_text"]
            return "".join([text.get("plain_text", "") for text in rich_text])
        
        elif block_type == "code":
            code_text = "".join([text.get("plain_text", "") for text in block_data.get("rich_text", [])])
            language = block_data.get("language", "")
            return f"```{language}\n{code_text}\n```"
        
        elif block_type == "equation":
            return block_data.get("expression", "")
        
        return ""
    
    def _extract_title(self, page: Dict[str, Any]) -> str:
        """Extract title from a Notion page."""
        properties = page.get("properties", {})
        
        for key, value in properties.items():
            if value.get("type") == "title":
                title_parts = value.get("title", [])
                return "".join([t.get("plain_text", "") for t in title_parts])
        
        return "Untitled"
    
    def _format_properties(self, properties: Dict[str, Any]) -> str:
        """Format Notion properties as text."""
        lines = []
        
        for key, value in properties.items():
            prop_type = value.get("type")
            
            if prop_type == "title":
                continue
            
            elif prop_type == "rich_text":
                text = "".join([t.get("plain_text", "") for t in value.get("rich_text", [])])
                if text:
                    lines.append(f"**{key}**: {text}")
            
            elif prop_type == "number":
                num = value.get("number")
                if num is not None:
                    lines.append(f"**{key}**: {num}")
            
            elif prop_type == "select":
                select_val = value.get("select")
                if select_val:
                    lines.append(f"**{key}**: {select_val.get('name', '')}")
            
            elif prop_type == "multi_select":
                options = value.get("multi_select", [])
                if options:
                    names = ", ".join([o.get("name", "") for o in options])
                    lines.append(f"**{key}**: {names}")
            
            elif prop_type == "date":
                date_val = value.get("date")
                if date_val:
                    lines.append(f"**{key}**: {date_val.get('start', '')}")
            
            elif prop_type == "checkbox":
                checked = value.get("checkbox", False)
                lines.append(f"**{key}**: {'☑' if checked else '☐'}")
            
            elif prop_type == "url":
                url = value.get("url")
                if url:
                    lines.append(f"**{key}**: {url}")
            
            elif prop_type == "email":
                email = value.get("email")
                if email:
                    lines.append(f"**{key}**: {email}")
        
        return "\n".join(lines)

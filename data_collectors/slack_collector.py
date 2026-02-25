#!/usr/bin/env python3
"""
Slack Data Collector
Collects messages, threads, and channel updates from Slack.
"""

import os
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

logger = logging.getLogger(__name__)


class SlackCollector:
    """Collects data from Slack workspace."""
    
    def __init__(self, token: Optional[str] = None):
        """
        Initialize Slack collector.
        
        Args:
            token: Slack bot/user token
        """
        slack_token = token or os.getenv("SLACK_BOT_TOKEN")
        if not slack_token:
            raise ValueError("Slack token is required")
        
        self.client = WebClient(token=slack_token)
        logger.info("Initialized Slack collector")
    
    def collect_channel_messages(
        self,
        channel_id: str,
        hours_back: int = 2
    ) -> List[Dict[str, Any]]:
        """
        Collect messages from a Slack channel.
        
        Args:
            channel_id: Slack channel ID
            hours_back: How many hours of history to collect
            
        Returns:
            List of collected documents
        """
        documents = []
        cutoff_time = datetime.utcnow() - timedelta(hours=hours_back)
        oldest_ts = cutoff_time.timestamp()
        
        try:
            response = self.client.conversations_history(
                channel=channel_id,
                oldest=str(oldest_ts),
                limit=1000
            )
            
            messages = response.get("messages", [])
            
            for message in messages:
                if message.get("type") != "message":
                    continue
                
                if "subtype" in message and message["subtype"] in ["channel_join", "channel_leave"]:
                    continue
                
                text = message.get("text", "")
                user_id = message.get("user", "Unknown")
                
                thread_replies = []
                if message.get("thread_ts"):
                    thread_replies = self._get_thread_replies(
                        channel_id,
                        message["thread_ts"]
                    )
                
                if thread_replies:
                    text += "\n\n## Thread Replies\n\n" + "\n\n".join(thread_replies)
                
                documents.append({
                    "text": text,
                    "metadata": {
                        "source": "slack",
                        "type": "message",
                        "channel_id": channel_id,
                        "user_id": user_id,
                        "message_ts": message.get("ts"),
                        "thread_ts": message.get("thread_ts"),
                        "has_thread": bool(message.get("thread_ts")),
                        "reply_count": message.get("reply_count", 0),
                        "created_at": datetime.fromtimestamp(
                            float(message.get("ts", 0))
                        ).isoformat(),
                        "collected_at": datetime.utcnow().isoformat()
                    }
                })
            
            logger.info(f"Collected {len(documents)} Slack messages from {channel_id}")
            
        except SlackApiError as e:
            logger.error(f"Error collecting Slack messages: {e}")
        
        return documents
    
    def collect_multiple_channels(
        self,
        channel_ids: List[str],
        hours_back: int = 2
    ) -> List[Dict[str, Any]]:
        """
        Collect messages from multiple Slack channels.
        
        Args:
            channel_ids: List of Slack channel IDs
            hours_back: How many hours of history to collect
            
        Returns:
            List of collected documents
        """
        all_documents = []
        
        for channel_id in channel_ids:
            try:
                documents = self.collect_channel_messages(channel_id, hours_back)
                all_documents.extend(documents)
            except Exception as e:
                logger.error(f"Error collecting from channel {channel_id}: {e}")
        
        return all_documents
    
    def collect_user_messages(
        self,
        user_id: str,
        hours_back: int = 2
    ) -> List[Dict[str, Any]]:
        """
        Collect messages from a specific user across all channels.
        
        Args:
            user_id: Slack user ID
            hours_back: How many hours of history to collect
            
        Returns:
            List of collected documents
        """
        documents = []
        cutoff_time = datetime.utcnow() - timedelta(hours=hours_back)
        oldest_ts = cutoff_time.timestamp()
        
        try:
            channels_response = self.client.conversations_list(
                types="public_channel,private_channel",
                limit=1000
            )
            
            for channel in channels_response.get("channels", []):
                channel_id = channel["id"]
                
                try:
                    response = self.client.conversations_history(
                        channel=channel_id,
                        oldest=str(oldest_ts),
                        limit=1000
                    )
                    
                    for message in response.get("messages", []):
                        if message.get("user") == user_id:
                            text = message.get("text", "")
                            
                            documents.append({
                                "text": text,
                                "metadata": {
                                    "source": "slack",
                                    "type": "user_message",
                                    "channel_id": channel_id,
                                    "channel_name": channel.get("name", ""),
                                    "user_id": user_id,
                                    "message_ts": message.get("ts"),
                                    "created_at": datetime.fromtimestamp(
                                        float(message.get("ts", 0))
                                    ).isoformat(),
                                    "collected_at": datetime.utcnow().isoformat()
                                }
                            })
                
                except SlackApiError as e:
                    logger.warning(f"Could not access channel {channel_id}: {e}")
            
            logger.info(f"Collected {len(documents)} messages from user {user_id}")
            
        except SlackApiError as e:
            logger.error(f"Error collecting user messages: {e}")
        
        return documents
    
    def _get_thread_replies(
        self,
        channel_id: str,
        thread_ts: str
    ) -> List[str]:
        """Get replies from a thread."""
        replies = []
        
        try:
            response = self.client.conversations_replies(
                channel=channel_id,
                ts=thread_ts
            )
            
            for message in response.get("messages", [])[1:]:
                user_id = message.get("user", "Unknown")
                text = message.get("text", "")
                replies.append(f"**{user_id}**: {text}")
        
        except SlackApiError as e:
            logger.warning(f"Error getting thread replies: {e}")
        
        return replies

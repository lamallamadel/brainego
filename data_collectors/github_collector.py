#!/usr/bin/env python3
"""
GitHub Data Collector
Collects issues, PRs, commits, and discussions from GitHub repositories.
"""

import os
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from github import Github, GithubException

logger = logging.getLogger(__name__)


class GitHubCollector:
    """Collects data from GitHub repositories."""
    
    def __init__(self, access_token: Optional[str] = None):
        """
        Initialize GitHub collector.
        
        Args:
            access_token: GitHub personal access token
        """
        token = access_token or os.getenv("GITHUB_TOKEN")
        if not token:
            raise ValueError("GitHub token is required")
        
        self.github = Github(token)
        self.user = self.github.get_user()
        logger.info(f"Initialized GitHub collector for user: {self.user.login}")
    
    def collect_repository_data(
        self,
        repo_name: str,
        hours_back: int = 6,
        include_issues: bool = True,
        include_prs: bool = True,
        include_commits: bool = True,
        include_discussions: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Collect data from a GitHub repository.
        
        Args:
            repo_name: Repository name in format "owner/repo"
            hours_back: How many hours of history to collect
            include_issues: Whether to collect issues
            include_prs: Whether to collect pull requests
            include_commits: Whether to collect commits
            include_discussions: Whether to collect discussions
            
        Returns:
            List of collected documents
        """
        documents = []
        cutoff_time = datetime.utcnow() - timedelta(hours=hours_back)
        
        try:
            repo = self.github.get_repo(repo_name)
            logger.info(f"Collecting data from {repo_name} since {cutoff_time}")
            
            if include_issues:
                documents.extend(self._collect_issues(repo, cutoff_time))
            
            if include_prs:
                documents.extend(self._collect_pull_requests(repo, cutoff_time))
            
            if include_commits:
                documents.extend(self._collect_commits(repo, cutoff_time))
            
            if include_discussions:
                documents.extend(self._collect_discussions(repo, cutoff_time))
            
            logger.info(f"Collected {len(documents)} documents from {repo_name}")
            return documents
            
        except GithubException as e:
            logger.error(f"Error accessing repository {repo_name}: {e}")
            raise
    
    def _collect_issues(
        self,
        repo,
        cutoff_time: datetime
    ) -> List[Dict[str, Any]]:
        """Collect issues from repository."""
        documents = []
        
        try:
            issues = repo.get_issues(
                state="all",
                since=cutoff_time,
                sort="updated",
                direction="desc"
            )
            
            for issue in issues:
                if issue.pull_request:
                    continue
                
                if issue.updated_at < cutoff_time:
                    break
                
                text = f"# {issue.title}\n\n{issue.body or ''}"
                
                comments = []
                for comment in issue.get_comments():
                    if comment.updated_at >= cutoff_time:
                        comments.append(f"{comment.user.login}: {comment.body}")
                
                if comments:
                    text += "\n\n## Comments\n\n" + "\n\n".join(comments)
                
                documents.append({
                    "text": text,
                    "metadata": {
                        "source": "github",
                        "type": "issue",
                        "repository": repo.full_name,
                        "issue_number": issue.number,
                        "issue_url": issue.html_url,
                        "state": issue.state,
                        "labels": [label.name for label in issue.labels],
                        "author": issue.user.login,
                        "created_at": issue.created_at.isoformat(),
                        "updated_at": issue.updated_at.isoformat(),
                        "collected_at": datetime.utcnow().isoformat()
                    }
                })
            
            logger.info(f"Collected {len(documents)} issues")
            
        except Exception as e:
            logger.error(f"Error collecting issues: {e}")
        
        return documents
    
    def _collect_pull_requests(
        self,
        repo,
        cutoff_time: datetime
    ) -> List[Dict[str, Any]]:
        """Collect pull requests from repository."""
        documents = []
        
        try:
            pulls = repo.get_pulls(
                state="all",
                sort="updated",
                direction="desc"
            )
            
            for pr in pulls:
                if pr.updated_at < cutoff_time:
                    break
                
                text = f"# {pr.title}\n\n{pr.body or ''}"
                
                comments = []
                for comment in pr.get_comments():
                    if comment.updated_at >= cutoff_time:
                        comments.append(f"{comment.user.login}: {comment.body}")
                
                for review in pr.get_reviews():
                    if review.submitted_at and review.submitted_at >= cutoff_time:
                        comments.append(f"{review.user.login} ({review.state}): {review.body or ''}")
                
                if comments:
                    text += "\n\n## Reviews and Comments\n\n" + "\n\n".join(comments)
                
                documents.append({
                    "text": text,
                    "metadata": {
                        "source": "github",
                        "type": "pull_request",
                        "repository": repo.full_name,
                        "pr_number": pr.number,
                        "pr_url": pr.html_url,
                        "state": pr.state,
                        "labels": [label.name for label in pr.labels],
                        "author": pr.user.login,
                        "created_at": pr.created_at.isoformat(),
                        "updated_at": pr.updated_at.isoformat(),
                        "merged": pr.merged,
                        "collected_at": datetime.utcnow().isoformat()
                    }
                })
            
            logger.info(f"Collected {len(documents)} pull requests")
            
        except Exception as e:
            logger.error(f"Error collecting pull requests: {e}")
        
        return documents
    
    def _collect_commits(
        self,
        repo,
        cutoff_time: datetime
    ) -> List[Dict[str, Any]]:
        """Collect commits from repository."""
        documents = []
        
        try:
            commits = repo.get_commits(since=cutoff_time)
            
            for commit in commits:
                commit_data = commit.commit
                
                text = f"# Commit: {commit_data.message}\n\n"
                text += f"Author: {commit_data.author.name}\n"
                text += f"SHA: {commit.sha}\n\n"
                
                files_changed = []
                for file in commit.files:
                    files_changed.append(
                        f"- {file.filename} (+{file.additions}/-{file.deletions})"
                    )
                
                if files_changed:
                    text += "## Files Changed\n\n" + "\n".join(files_changed)
                
                documents.append({
                    "text": text,
                    "metadata": {
                        "source": "github",
                        "type": "commit",
                        "repository": repo.full_name,
                        "commit_sha": commit.sha,
                        "commit_url": commit.html_url,
                        "author": commit_data.author.name,
                        "author_email": commit_data.author.email,
                        "committed_at": commit_data.author.date.isoformat(),
                        "files_changed": len(commit.files),
                        "collected_at": datetime.utcnow().isoformat()
                    }
                })
            
            logger.info(f"Collected {len(documents)} commits")
            
        except Exception as e:
            logger.error(f"Error collecting commits: {e}")
        
        return documents
    
    def _collect_discussions(
        self,
        repo,
        cutoff_time: datetime
    ) -> List[Dict[str, Any]]:
        """Collect discussions from repository."""
        documents = []
        
        try:
            logger.info("Discussions collection is limited via API")
            
        except Exception as e:
            logger.error(f"Error collecting discussions: {e}")
        
        return documents
    
    def collect_user_activity(
        self,
        hours_back: int = 6
    ) -> List[Dict[str, Any]]:
        """
        Collect user's recent activity across all repositories.
        
        Args:
            hours_back: How many hours of history to collect
            
        Returns:
            List of collected documents
        """
        documents = []
        cutoff_time = datetime.utcnow() - timedelta(hours=hours_back)
        
        try:
            events = self.user.get_events()
            
            for event in events[:100]:
                if event.created_at < cutoff_time:
                    break
                
                if event.type in ["IssuesEvent", "PullRequestEvent", "PushEvent", "IssueCommentEvent"]:
                    documents.append({
                        "text": f"Event: {event.type}\nRepo: {event.repo.name}\n{str(event.payload)}",
                        "metadata": {
                            "source": "github",
                            "type": "user_event",
                            "event_type": event.type,
                            "repository": event.repo.name,
                            "created_at": event.created_at.isoformat(),
                            "collected_at": datetime.utcnow().isoformat()
                        }
                    })
            
            logger.info(f"Collected {len(documents)} user activity events")
            
        except Exception as e:
            logger.error(f"Error collecting user activity: {e}")
        
        return documents

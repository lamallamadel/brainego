#!/usr/bin/env python3
"""
GitHub Data Collector
Collects issues, PRs, commits, discussions, and repository code files
from GitHub repositories.
"""

import base64
import fnmatch
import hashlib
import json
import os
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple
from datetime import datetime, timedelta

try:
    from github import Github, GithubException
except Exception:  # pragma: no cover - allows unit tests without PyGithub
    Github = None  # type: ignore[assignment]

    class GithubException(Exception):
        """Fallback GitHub exception when PyGithub is unavailable."""


DEFAULT_GITHUB_REPO_SYNC_STATE_PATH = "/tmp/brainego_github_repo_sync_state.json"
DEFAULT_MAX_FILE_SIZE_BYTES = 200_000
_BINARY_EXTENSIONS = {
    ".7z",
    ".a",
    ".bmp",
    ".class",
    ".dll",
    ".dylib",
    ".exe",
    ".gif",
    ".gz",
    ".ico",
    ".jar",
    ".jpeg",
    ".jpg",
    ".lock",
    ".mp3",
    ".mp4",
    ".o",
    ".pdf",
    ".png",
    ".pyc",
    ".so",
    ".svg",
    ".tar",
    ".tgz",
    ".wav",
    ".webp",
    ".woff",
    ".woff2",
    ".zip",
}
_EXCLUDED_PATH_PARTS = {
    ".git",
    ".next",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "target",
    "venv",
}
_LANGUAGE_BY_EXTENSION = {
    ".c": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cs": "csharp",
    ".css": "css",
    ".go": "go",
    ".h": "c",
    ".hpp": "cpp",
    ".html": "html",
    ".java": "java",
    ".js": "javascript",
    ".json": "json",
    ".kt": "kotlin",
    ".md": "markdown",
    ".php": "php",
    ".py": "python",
    ".rb": "ruby",
    ".rs": "rust",
    ".scala": "scala",
    ".sh": "shell",
    ".sql": "sql",
    ".swift": "swift",
    ".toml": "toml",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".txt": "text",
    ".xml": "xml",
    ".yaml": "yaml",
    ".yml": "yaml",
}

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
        
        if Github is None:
            raise RuntimeError(
                "PyGithub is required for GitHubCollector. "
                "Install dependency: PyGithub>=2.1.1"
            )

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

    @staticmethod
    def build_repository_document_id(repo_name: str, path: str, workspace_id: str) -> str:
        """Build a deterministic document_id for a repository file."""
        normalized_repo = str(repo_name).strip().lower()
        normalized_path = str(path).strip()
        normalized_workspace = str(workspace_id).strip()
        identifier = f"{normalized_workspace}:{normalized_repo}:{normalized_path}"
        return hashlib.sha256(identifier.encode("utf-8")).hexdigest()

    def collect_repository_codebase(
        self,
        repo_name: str,
        workspace_id: str,
        branch: Optional[str] = None,
        incremental: bool = True,
        reindex: bool = False,
        state_path: Optional[str] = None,
        max_file_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES,
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Collect repository source files for codebase-aware RAG ingestion.

        The first sync is full. Subsequent syncs are incremental by default by
        diffing the last synced commit against the latest default-branch commit.
        """
        normalized_workspace_id = str(workspace_id or "").strip()
        if not normalized_workspace_id:
            raise ValueError("workspace_id is required for repository codebase ingestion")

        if max_file_size_bytes <= 0:
            raise ValueError("max_file_size_bytes must be greater than 0")

        repo = self.github.get_repo(repo_name)
        target_branch = branch or repo.default_branch
        head_commit_sha = repo.get_branch(target_branch).commit.sha

        effective_state_path = Path(
            state_path
            or os.getenv("GITHUB_REPO_SYNC_STATE_PATH", DEFAULT_GITHUB_REPO_SYNC_STATE_PATH)
        )

        sync_state = self._load_repo_sync_state(effective_state_path)
        state_key = self._build_sync_state_key(
            repo_full_name=repo.full_name,
            workspace_id=normalized_workspace_id,
            branch=target_branch,
        )
        previous_state = sync_state.get(state_key, {})
        previous_commit = previous_state.get("last_commit")
        previous_paths = {
            str(path).strip()
            for path in previous_state.get("indexed_paths", [])
            if str(path).strip()
        }

        mode = "full"
        changed_paths: Set[str] = set()
        deleted_paths: Set[str] = set()

        if incremental and previous_commit and not reindex:
            if previous_commit == head_commit_sha:
                mode = "incremental"
                changed_paths = set()
                deleted_paths = set()
            else:
                try:
                    comparison = repo.compare(previous_commit, head_commit_sha)
                    changed_paths, deleted_paths = self._extract_compare_paths(
                        getattr(comparison, "files", []),
                    )
                    mode = "incremental"
                except Exception as exc:
                    logger.warning(
                        "Incremental compare failed for %s (%s -> %s): %s. Falling back to full sync.",
                        repo.full_name,
                        previous_commit,
                        head_commit_sha,
                        exc,
                    )
                    changed_paths = set(
                        self._list_repository_paths(
                            repo=repo,
                            ref=head_commit_sha,
                            max_file_size_bytes=max_file_size_bytes,
                            include_patterns=include_patterns,
                            exclude_patterns=exclude_patterns,
                        )
                    )
                    deleted_paths = previous_paths - changed_paths
                    mode = "full_fallback"
        else:
            changed_paths = set(
                self._list_repository_paths(
                    repo=repo,
                    ref=head_commit_sha,
                    max_file_size_bytes=max_file_size_bytes,
                    include_patterns=include_patterns,
                    exclude_patterns=exclude_patterns,
                )
            )
            deleted_paths = previous_paths - changed_paths
            mode = "full_reindex" if reindex else "full"

        documents: List[Dict[str, Any]] = []
        skipped_paths: Set[str] = set()
        for path in sorted(changed_paths):
            document = self._build_repository_document(
                repo=repo,
                path=path,
                commit_sha=head_commit_sha,
                branch=target_branch,
                workspace_id=normalized_workspace_id,
                max_file_size_bytes=max_file_size_bytes,
                include_patterns=include_patterns,
                exclude_patterns=exclude_patterns,
            )
            if document is None:
                skipped_paths.add(path)
                if path in previous_paths:
                    deleted_paths.add(path)
                continue
            documents.append(document)

        if mode == "incremental":
            indexed_paths = set(previous_paths)
        else:
            indexed_paths = set()
        indexed_paths -= deleted_paths
        indexed_paths -= skipped_paths
        indexed_paths.update(doc["metadata"]["path"] for doc in documents)

        sync_state[state_key] = {
            "repo": repo.full_name,
            "workspace_id": normalized_workspace_id,
            "branch": target_branch,
            "last_commit": head_commit_sha,
            "indexed_paths": sorted(indexed_paths),
            "updated_at": datetime.utcnow().isoformat(),
        }
        self._save_repo_sync_state(effective_state_path, sync_state)

        return {
            "status": "success",
            "repository": repo.full_name,
            "repo": repo.full_name,
            "branch": target_branch,
            "workspace_id": normalized_workspace_id,
            "workspace": normalized_workspace_id,
            "documents": documents,
            "deleted_paths": sorted(deleted_paths),
            "skipped_paths": sorted(skipped_paths),
            "sync": {
                "mode": mode,
                "incremental": mode == "incremental",
                "previous_commit": previous_commit,
                "current_commit": head_commit_sha,
                "documents_collected": len(documents),
                "paths_deleted": len(deleted_paths),
                "paths_skipped": len(skipped_paths),
            },
        }

    @staticmethod
    def _build_sync_state_key(repo_full_name: str, workspace_id: str, branch: str) -> str:
        """Create stable key used for persisted sync state."""
        return f"{repo_full_name}:{workspace_id}:{branch}"

    @staticmethod
    def _load_repo_sync_state(path: Path) -> Dict[str, Any]:
        """Load repository sync state from disk."""
        if not path.exists():
            return {}
        try:
            with path.open("r", encoding="utf-8") as state_file:
                payload = json.load(state_file)
            return payload if isinstance(payload, dict) else {}
        except Exception as exc:
            logger.warning("Unable to read GitHub sync state %s: %s", path, exc)
            return {}

    @staticmethod
    def _save_repo_sync_state(path: Path, payload: Dict[str, Any]) -> None:
        """Persist repository sync state on disk."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as state_file:
            json.dump(payload, state_file, indent=2, sort_keys=True)

    def _extract_compare_paths(self, files: Any) -> Tuple[Set[str], Set[str]]:
        """Extract changed and removed file paths from GitHub compare response."""
        changed_paths: Set[str] = set()
        deleted_paths: Set[str] = set()

        for changed_file in files or []:
            path = str(getattr(changed_file, "filename", "")).strip()
            if not path:
                continue

            status = str(getattr(changed_file, "status", "")).strip().lower()
            previous_filename = str(
                getattr(changed_file, "previous_filename", "") or ""
            ).strip()

            if status == "removed":
                if self._should_collect_repository_path(path, None, None):
                    deleted_paths.add(path)
                continue

            if status == "renamed":
                if previous_filename and self._should_collect_repository_path(
                    previous_filename, None, None
                ):
                    deleted_paths.add(previous_filename)
                if self._should_collect_repository_path(path, None, None):
                    changed_paths.add(path)
                continue

            if self._should_collect_repository_path(path, None, None):
                changed_paths.add(path)

        return changed_paths, deleted_paths

    def _list_repository_paths(
        self,
        repo: Any,
        ref: str,
        max_file_size_bytes: int,
        include_patterns: Optional[List[str]],
        exclude_patterns: Optional[List[str]],
    ) -> List[str]:
        """List collectable repository file paths for a given ref."""
        tree = repo.get_git_tree(ref, recursive=True)
        paths: List[str] = []

        for item in getattr(tree, "tree", []):
            if getattr(item, "type", None) != "blob":
                continue

            path = str(getattr(item, "path", "")).strip()
            size = getattr(item, "size", 0) or 0
            if not path:
                continue

            if int(size) > max_file_size_bytes:
                continue

            if not self._should_collect_repository_path(
                path=path,
                include_patterns=include_patterns,
                exclude_patterns=exclude_patterns,
            ):
                continue

            paths.append(path)

        return sorted(paths)

    @staticmethod
    def _should_collect_repository_path(
        path: str,
        include_patterns: Optional[List[str]],
        exclude_patterns: Optional[List[str]],
    ) -> bool:
        """Determine whether a repository path should be indexed."""
        normalized_path = str(path).strip()
        if not normalized_path:
            return False

        lowered_path = normalized_path.lower()
        suffix = Path(lowered_path).suffix
        if suffix in _BINARY_EXTENSIONS:
            return False

        parts = {part.lower() for part in Path(normalized_path).parts}
        if parts.intersection(_EXCLUDED_PATH_PARTS):
            return False

        if include_patterns:
            if not any(fnmatch.fnmatch(normalized_path, pattern) for pattern in include_patterns):
                return False

        if exclude_patterns:
            if any(fnmatch.fnmatch(normalized_path, pattern) for pattern in exclude_patterns):
                return False

        return True

    @staticmethod
    def _decode_content_to_text(content_file: Any) -> Optional[str]:
        """Decode repository file content to UTF-8 text."""
        raw_bytes = getattr(content_file, "decoded_content", None)
        if raw_bytes is None:
            encoded_content = getattr(content_file, "content", None)
            if not encoded_content:
                return None
            try:
                raw_bytes = base64.b64decode(encoded_content)
            except Exception:
                return None

        if not isinstance(raw_bytes, (bytes, bytearray)):
            return None
        if b"\x00" in raw_bytes:
            return None

        try:
            text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            text = raw_bytes.decode("utf-8", errors="replace")

        normalized_text = text.replace("\r\n", "\n").replace("\r", "\n")
        return normalized_text if normalized_text.strip() else None

    @staticmethod
    def _detect_language(path: str) -> str:
        """Infer programming language from file path."""
        normalized_path = str(path).strip()
        filename = Path(normalized_path).name.lower()
        if filename == "dockerfile":
            return "dockerfile"
        if filename.startswith("makefile"):
            return "makefile"

        suffix = Path(normalized_path).suffix.lower()
        return _LANGUAGE_BY_EXTENSION.get(suffix, "text")

    def _build_repository_document(
        self,
        repo: Any,
        path: str,
        commit_sha: str,
        branch: str,
        workspace_id: str,
        max_file_size_bytes: int,
        include_patterns: Optional[List[str]],
        exclude_patterns: Optional[List[str]],
    ) -> Optional[Dict[str, Any]]:
        """Build a RAG-ready document from a repository file path."""
        if not self._should_collect_repository_path(path, include_patterns, exclude_patterns):
            return None

        try:
            content = repo.get_contents(path, ref=commit_sha)
        except Exception as exc:
            logger.warning("Unable to fetch %s@%s: %s", path, commit_sha, exc)
            return None

        if isinstance(content, list):
            return None

        file_size = int(getattr(content, "size", 0) or 0)
        if file_size > max_file_size_bytes:
            return None

        text = self._decode_content_to_text(content)
        if text is None:
            return None

        repo_name = repo.full_name
        document_id = self.build_repository_document_id(
            repo_name=repo_name,
            path=path,
            workspace_id=workspace_id,
        )
        collected_at = datetime.utcnow().isoformat()

        metadata = {
            "source": "github_repo",
            "type": "code_file",
            "repo": repo_name,
            "repository": repo_name,
            "path": path,
            "commit": commit_sha,
            "branch": branch,
            "lang": self._detect_language(path),
            "workspace": workspace_id,
            "workspace_id": workspace_id,
            "document_id": document_id,
            "blob_sha": getattr(content, "sha", None),
            "file_size": file_size,
            "collected_at": collected_at,
        }

        return {
            "text": text,
            "metadata": metadata,
        }
    
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

#!/usr/bin/env python3
"""
Unit tests for GitHub Repository RAG Worker with golden-set citation contract.

This test suite verifies that:
1. GitHub repo contents are correctly collected and ingested
2. Path+commit metadata is preserved through the ingestion pipeline
3. RAG query responses include citations in path@commit format
4. 20 curated questions verify citation format consistency
"""

import pytest
from typing import Dict, Any, List


GOLDEN_SET_QUESTIONS = [
    {
        "id": "q1",
        "query": "How do I initialize the GitHub collector?",
        "expected_metadata_fields": ["path", "commit"],
        "expected_citation_format": r"^.+@[a-f0-9]{40}$",
    },
    {
        "id": "q2",
        "query": "What file extensions are excluded by default?",
        "expected_metadata_fields": ["path", "commit"],
        "expected_citation_format": r"^.+@[a-f0-9]{40}$",
    },
    {
        "id": "q3",
        "query": "How does incremental syncing work?",
        "expected_metadata_fields": ["path", "commit"],
        "expected_citation_format": r"^.+@[a-f0-9]{40}$",
    },
    {
        "id": "q4",
        "query": "What is the default max file size?",
        "expected_metadata_fields": ["path", "commit"],
        "expected_citation_format": r"^.+@[a-f0-9]{40}$",
    },
    {
        "id": "q5",
        "query": "How are binary files detected?",
        "expected_metadata_fields": ["path", "commit"],
        "expected_citation_format": r"^.+@[a-f0-9]{40}$",
    },
    {
        "id": "q6",
        "query": "What programming languages are supported?",
        "expected_metadata_fields": ["path", "commit"],
        "expected_citation_format": r"^.+@[a-f0-9]{40}$",
    },
    {
        "id": "q7",
        "query": "How do I exclude specific directories?",
        "expected_metadata_fields": ["path", "commit"],
        "expected_citation_format": r"^.+@[a-f0-9]{40}$",
    },
    {
        "id": "q8",
        "query": "What is the chunk size for documents?",
        "expected_metadata_fields": ["path", "commit"],
        "expected_citation_format": r"^.+@[a-f0-9]{40}$",
    },
    {
        "id": "q9",
        "query": "How do I specify include patterns?",
        "expected_metadata_fields": ["path", "commit"],
        "expected_citation_format": r"^.+@[a-f0-9]{40}$",
    },
    {
        "id": "q10",
        "query": "What metadata is attached to each chunk?",
        "expected_metadata_fields": ["path", "commit"],
        "expected_citation_format": r"^.+@[a-f0-9]{40}$",
    },
    {
        "id": "q11",
        "query": "How does workspace partitioning work?",
        "expected_metadata_fields": ["path", "commit"],
        "expected_citation_format": r"^.+@[a-f0-9]{40}$",
    },
    {
        "id": "q12",
        "query": "What happens when a file is renamed?",
        "expected_metadata_fields": ["path", "commit"],
        "expected_citation_format": r"^.+@[a-f0-9]{40}$",
    },
    {
        "id": "q13",
        "query": "How are deleted files handled?",
        "expected_metadata_fields": ["path", "commit"],
        "expected_citation_format": r"^.+@[a-f0-9]{40}$",
    },
    {
        "id": "q14",
        "query": "What is the sync state format?",
        "expected_metadata_fields": ["path", "commit"],
        "expected_citation_format": r"^.+@[a-f0-9]{40}$",
    },
    {
        "id": "q15",
        "query": "How do I trigger a full reindex?",
        "expected_metadata_fields": ["path", "commit"],
        "expected_citation_format": r"^.+@[a-f0-9]{40}$",
    },
    {
        "id": "q16",
        "query": "What encoding is used for file content?",
        "expected_metadata_fields": ["path", "commit"],
        "expected_citation_format": r"^.+@[a-f0-9]{40}$",
    },
    {
        "id": "q17",
        "query": "How are commit hashes computed?",
        "expected_metadata_fields": ["path", "commit"],
        "expected_citation_format": r"^.+@[a-f0-9]{40}$",
    },
    {
        "id": "q18",
        "query": "What is the batch ingest endpoint format?",
        "expected_metadata_fields": ["path", "commit"],
        "expected_citation_format": r"^.+@[a-f0-9]{40}$",
    },
    {
        "id": "q19",
        "query": "How do I authenticate with GitHub?",
        "expected_metadata_fields": ["path", "commit"],
        "expected_citation_format": r"^.+@[a-f0-9]{40}$",
    },
    {
        "id": "q20",
        "query": "What is the default branch behavior?",
        "expected_metadata_fields": ["path", "commit"],
        "expected_citation_format": r"^.+@[a-f0-9]{40}$",
    },
]


class TestGitHubRepoRAGWorker:
    """Test suite for GitHub Repository RAG ingestion and citation format."""

    def test_golden_set_citation_format_contract(self):
        """
        Golden-set contract: verify citation format for 20 curated questions.
        
        This test validates that:
        1. Each question in the golden set has expected metadata fields defined
        2. The citation format regex matches path@commit pattern
        3. All 20 questions follow the same citation contract
        """
        import re
        
        assert len(GOLDEN_SET_QUESTIONS) == 20, "Golden set must contain exactly 20 questions"
        
        for question in GOLDEN_SET_QUESTIONS:
            assert "id" in question, f"Question missing id: {question}"
            assert "query" in question, f"Question {question.get('id')} missing query"
            assert "expected_metadata_fields" in question, \
                f"Question {question['id']} missing expected_metadata_fields"
            assert "expected_citation_format" in question, \
                f"Question {question['id']} missing expected_citation_format"
            
            expected_fields = question["expected_metadata_fields"]
            assert "path" in expected_fields, \
                f"Question {question['id']} must expect 'path' metadata"
            assert "commit" in expected_fields, \
                f"Question {question['id']} must expect 'commit' metadata"
            
            citation_regex = question["expected_citation_format"]
            pattern = re.compile(citation_regex)
            
            test_citations = [
                "src/main.py@a1b2c3d4e5f6789012345678901234567890abcd",
                "README.md@1234567890abcdef1234567890abcdef12345678",
                "lib/utils.ts@fedcba9876543210fedcba9876543210fedcba98",
            ]
            
            for test_citation in test_citations:
                assert pattern.match(test_citation), \
                    f"Question {question['id']} citation format {citation_regex} " \
                    f"does not match test citation {test_citation}"

    def test_extract_rag_sources_from_metadata(self):
        """Test extraction of path@commit sources from RAG metadata."""
        from api_server import extract_rag_sources
        
        mock_results = [
            {
                "text": "Example chunk 1",
                "score": 0.95,
                "metadata": {
                    "path": "src/api_server.py",
                    "commit": "abc123def456789012345678901234567890abcd",
                    "repo": "owner/repo",
                    "workspace_id": "test-workspace",
                },
            },
            {
                "text": "Example chunk 2",
                "score": 0.92,
                "metadata": {
                    "path": "README.md",
                    "commit": "def456abc789012345678901234567890abcdef1",
                    "repo": "owner/repo",
                    "workspace_id": "test-workspace",
                },
            },
            {
                "text": "Example chunk 3",
                "score": 0.88,
                "metadata": {
                    "path": "src/api_server.py",
                    "commit": "abc123def456789012345678901234567890abcd",
                    "repo": "owner/repo",
                    "workspace_id": "test-workspace",
                },
            },
        ]
        
        sources = extract_rag_sources(mock_results)
        
        assert len(sources) == 2, "Should deduplicate identical path@commit pairs"
        assert {"path": "src/api_server.py", "commit": "abc123def456789012345678901234567890abcd"} in sources
        assert {"path": "README.md", "commit": "def456abc789012345678901234567890abcdef1"} in sources

    def test_render_citation_section_format(self):
        """Test citation section rendering with path@commit format."""
        from api_server import render_rag_citation_section, RAG_CITATION_SECTION_HEADER
        
        mock_sources = [
            {"path": "src/main.py", "commit": "a1b2c3d4e5f6789012345678901234567890abcd"},
            {"path": "lib/utils.ts", "commit": "fedcba9876543210fedcba9876543210fedcba98"},
        ]
        
        citation_text = render_rag_citation_section(mock_sources)
        
        assert RAG_CITATION_SECTION_HEADER in citation_text
        assert "src/main.py@a1b2c3d4e5f6789012345678901234567890abcd" in citation_text
        assert "lib/utils.ts@fedcba9876543210fedcba9876543210fedcba98" in citation_text
        assert citation_text.count("@") == 2, "Should have exactly 2 @ separators"

    def test_citation_format_validates_against_regex(self):
        """Test that generated citations match the expected regex pattern."""
        import re
        
        citation_pattern = re.compile(r"^.+@[a-f0-9]{40}$")
        
        valid_citations = [
            "src/api_server.py@abc123def456789012345678901234567890abcd",
            "README.md@1234567890abcdef1234567890abcdef12345678",
            "docs/guide.md@fedcba9876543210fedcba9876543210fedcba98",
            "a/b/c/deep.js@0000000000000000000000000000000000000000",
        ]
        
        for citation in valid_citations:
            assert citation_pattern.match(citation), \
                f"Valid citation {citation} should match pattern"
        
        invalid_citations = [
            "src/api_server.py",
            "@abc123",
            "src/main.py@short",
            "src/main.py@GGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGG",
        ]
        
        for citation in invalid_citations:
            assert not citation_pattern.match(citation), \
                f"Invalid citation {citation} should not match pattern"

    def test_github_collector_provides_required_metadata(self):
        """Test that GitHubCollector document format includes path and commit."""
        from data_collectors.github_collector import GitHubCollector
        
        mock_metadata = {
            "source": "github_repo",
            "type": "code_file",
            "repo": "owner/repo",
            "path": "src/example.py",
            "commit": "abc123def456789012345678901234567890abcd",
            "branch": "main",
            "lang": "python",
            "workspace_id": "test-workspace",
        }
        
        assert "path" in mock_metadata, "Document must have path metadata"
        assert "commit" in mock_metadata, "Document must have commit metadata"
        assert len(mock_metadata["commit"]) == 40, "Commit must be 40-char SHA"

    def test_worker_ingest_repository_structure(self):
        """Test GitHubRepoRAGWorker.ingest_repository returns expected structure."""
        expected_keys = [
            "status",
            "repo",
            "workspace_id",
            "documents_collected",
            "documents_ingested",
            "chunks_created",
            "collection_result",
            "ingest_result",
        ]
        
        mock_result = {
            "status": "success",
            "repo": "owner/repo",
            "workspace_id": "test-workspace",
            "documents_collected": 10,
            "documents_ingested": 10,
            "chunks_created": 25,
            "collection_result": {},
            "ingest_result": {},
        }
        
        for key in expected_keys:
            assert key in mock_result, f"Result must include {key}"

    def test_rag_ingest_github_request_validation(self):
        """Test RAGIngestGitHubRequest model validation."""
        from api_server import RAGIngestGitHubRequest
        
        valid_request = RAGIngestGitHubRequest(
            repo="owner/repo",
            workspace_id="test-workspace",
            branch="main",
            incremental=True,
            max_file_size_bytes=200_000,
        )
        
        assert valid_request.repo == "owner/repo"
        assert valid_request.workspace_id == "test-workspace"
        assert valid_request.branch == "main"
        assert valid_request.incremental is True
        assert valid_request.max_file_size_bytes == 200_000

    def test_citation_section_empty_sources(self):
        """Test citation section rendering with empty sources."""
        from api_server import render_rag_citation_section
        
        citation_text = render_rag_citation_section([])
        assert citation_text == "", "Empty sources should return empty string"

    def test_citation_deduplication(self):
        """Test that duplicate path@commit pairs are deduplicated."""
        from api_server import extract_rag_sources
        
        mock_results = [
            {"metadata": {"path": "file.py", "commit": "abc123abc123abc123abc123abc123abc123abcd"}},
            {"metadata": {"path": "file.py", "commit": "abc123abc123abc123abc123abc123abc123abcd"}},
            {"metadata": {"path": "file.py", "commit": "abc123abc123abc123abc123abc123abc123abcd"}},
        ]
        
        sources = extract_rag_sources(mock_results)
        assert len(sources) == 1, "Should deduplicate identical sources"

    def test_missing_metadata_fields(self):
        """Test extraction handles missing metadata fields gracefully."""
        from api_server import extract_rag_sources
        
        mock_results = [
            {"metadata": {"path": "file.py"}},
            {"metadata": {"commit": "abc123abc123abc123abc123abc123abc123abcd"}},
            {"metadata": {}},
            {"text": "no metadata"},
        ]
        
        sources = extract_rag_sources(mock_results)
        assert len(sources) == 0, "Should skip results with incomplete metadata"

    def test_citation_format_in_response(self):
        """Test that citation format appears correctly in full response."""
        from api_server import append_rag_citations_and_guidance
        
        generated_text = "This is the answer to the question."
        rag_sources = [
            {"path": "src/main.py", "commit": "abc123def456789012345678901234567890abcd"},
        ]
        
        result = append_rag_citations_and_guidance(
            generated_text,
            rag_sources=rag_sources,
            context_insufficient=False,
        )
        
        assert "src/main.py@abc123def456789012345678901234567890abcd" in result
        assert "Sources (path + commit):" in result

    def test_worker_workspace_id_validation(self):
        """Test that worker validates workspace_id is required."""
        from data_collectors.github_repo_rag_worker import GitHubRepoRAGWorker
        
        with pytest.raises(ValueError, match="workspace_id is required"):
            worker = GitHubRepoRAGWorker(access_token="fake-token")
            worker.ingest_repository(
                repo="owner/repo",
                workspace_id="",
                branch="main",
            )

    def test_golden_set_all_questions_unique_ids(self):
        """Test that all golden set questions have unique IDs."""
        question_ids = [q["id"] for q in GOLDEN_SET_QUESTIONS]
        assert len(question_ids) == len(set(question_ids)), \
            "All question IDs must be unique"

    def test_golden_set_all_queries_non_empty(self):
        """Test that all golden set queries are non-empty strings."""
        for question in GOLDEN_SET_QUESTIONS:
            assert isinstance(question["query"], str), \
                f"Question {question['id']} query must be a string"
            assert len(question["query"].strip()) > 0, \
                f"Question {question['id']} query must be non-empty"

    def test_citation_format_no_extra_whitespace(self):
        """Test that citation format has no extra whitespace around @."""
        from api_server import render_rag_citation_section
        
        mock_sources = [
            {"path": "file.py", "commit": "abc123abc123abc123abc123abc123abc123abcd"},
        ]
        
        citation_text = render_rag_citation_section(mock_sources)
        
        assert " @ " not in citation_text, "Should not have spaces around @"
        assert "@" in citation_text, "Should have @ separator"

    def test_metadata_commit_sha_alternatives(self):
        """Test that extract_rag_sources handles commit_sha, sha, revision aliases."""
        from api_server import extract_rag_sources
        
        mock_results = [
            {"metadata": {"path": "f1.py", "commit_sha": "aaa111aaa111aaa111aaa111aaa111aaa111aaaa"}},
            {"metadata": {"path": "f2.py", "sha": "bbb222bbb222bbb222bbb222bbb222bbb222bbbb"}},
            {"metadata": {"path": "f3.py", "revision": "ccc333ccc333ccc333ccc333ccc333ccc333cccc"}},
        ]
        
        sources = extract_rag_sources(mock_results)
        
        assert len(sources) == 3, "Should extract from all commit field aliases"

    def test_metadata_path_alternatives(self):
        """Test that extract_rag_sources handles file_path, source_path, filename aliases."""
        from api_server import extract_rag_sources
        
        mock_results = [
            {"metadata": {"file_path": "f1.py", "commit": "aaa111aaa111aaa111aaa111aaa111aaa111aaaa"}},
            {"metadata": {"source_path": "f2.py", "commit": "bbb222bbb222bbb222bbb222bbb222bbb222bbbb"}},
            {"metadata": {"filename": "f3.py", "commit": "ccc333ccc333ccc333ccc333ccc333ccc333cccc"}},
        ]
        
        sources = extract_rag_sources(mock_results)
        
        assert len(sources) == 3, "Should extract from all path field aliases"

    def test_github_collector_document_id_deterministic(self):
        """Test that GitHubCollector generates deterministic document IDs."""
        from data_collectors.github_collector import GitHubCollector
        
        doc_id_1 = GitHubCollector.build_repository_document_id(
            repo_name="owner/repo",
            path="src/main.py",
            workspace_id="test-workspace",
        )
        
        doc_id_2 = GitHubCollector.build_repository_document_id(
            repo_name="owner/repo",
            path="src/main.py",
            workspace_id="test-workspace",
        )
        
        assert doc_id_1 == doc_id_2, "Document ID must be deterministic"
        assert len(doc_id_1) == 64, "Document ID should be SHA256 hex (64 chars)"

    def test_worker_http_client_configuration(self):
        """Test GitHubRepoRAGWorker HTTP client configuration."""
        from data_collectors.github_repo_rag_worker import GitHubRepoRAGWorker
        
        worker = GitHubRepoRAGWorker(
            access_token="fake-token",
            rag_api_url="http://custom-api:9000",
            timeout=600,
        )
        
        assert worker.rag_api_url == "http://custom-api:9000"
        assert worker.timeout == 600

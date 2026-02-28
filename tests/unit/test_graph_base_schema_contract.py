"""Contract checks for AFR-41 Neo4j deployment and base graph schema."""

from pathlib import Path

import pytest


@pytest.mark.unit
def test_base_schema_file_defines_required_node_labels_and_relationships():
    schema = Path("configs/neo4j/base_schema.cypher").read_text()

    for label in ["Project", "Person", "Concept", "Document", "Problem", "Lesson"]:
        assert f":{label}" in schema

    for relation in ["WORKS_ON", "RELATES_TO", "CAUSED_BY", "SOLVED_BY", "LEARNED_FROM"]:
        assert f":{relation}" in schema


@pytest.mark.unit
def test_docker_compose_exposes_neo4j_service():
    compose = Path("docker-compose.yaml").read_text()

    assert "neo4j:" in compose
    assert "neo4j:5.15-community" in compose
    assert '"7474:7474"' in compose
    assert '"7687:7687"' in compose


@pytest.mark.unit
def test_api_server_exposes_simple_cypher_query_endpoint():
    api_server = Path("api_server.py").read_text()

    assert '@app.post("/graph/query"' in api_server
    assert "Execute Cypher query on knowledge graph" in api_server
    assert "service.query_graph(" in api_server

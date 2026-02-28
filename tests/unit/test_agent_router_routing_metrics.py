"""Static checks for AgentRouter routing config and per-model fallback metrics."""

from pathlib import Path


AGENT_ROUTER_SOURCE = Path("agent_router.py").read_text(encoding="utf-8")
ROUTER_CONFIG_SOURCE = Path("configs/agent-router.yaml").read_text(encoding="utf-8")


def test_routing_config_maps_intents_to_primary_models():
    """Routing YAML should map code/reasoning/general intents to primary models."""
    assert "primary_model:" in ROUTER_CONFIG_SOURCE
    assert 'code: "qwen-coder"' in ROUTER_CONFIG_SOURCE
    assert 'reasoning: "deepseek-r1"' in ROUTER_CONFIG_SOURCE
    assert 'general: "llama"' in ROUTER_CONFIG_SOURCE


def test_routing_config_declares_fallback_chain_for_each_model():
    """Routing YAML should declare explicit fallback chains for every primary model."""
    assert "fallback_chains:" in ROUTER_CONFIG_SOURCE
    assert 'qwen-coder: ["llama", "deepseek-r1"]' in ROUTER_CONFIG_SOURCE
    assert 'deepseek-r1: ["llama", "qwen-coder"]' in ROUTER_CONFIG_SOURCE
    assert 'llama: ["qwen-coder", "deepseek-r1"]' in ROUTER_CONFIG_SOURCE


def test_agent_router_exposes_model_request_and_fallback_metrics():
    """Router should expose per-model request and fallback metrics."""
    assert "agent_router_model_requests_total" in AGENT_ROUTER_SOURCE
    assert "agent_router_model_fallbacks_total" in AGENT_ROUTER_SOURCE
    assert "['model', 'role']" in AGENT_ROUTER_SOURCE
    assert "role='source'" in AGENT_ROUTER_SOURCE
    assert "role='target'" in AGENT_ROUTER_SOURCE

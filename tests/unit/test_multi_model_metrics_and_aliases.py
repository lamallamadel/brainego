"""Static regression tests for multi-model routing and metrics wiring."""

from pathlib import Path


API_SERVER_SOURCE = Path("api_server.py").read_text(encoding="utf-8")
AGENT_ROUTER_SOURCE = Path("agent_router.py").read_text(encoding="utf-8")
ROUTER_CONFIG_SOURCE = Path("configs/agent-router.yaml").read_text(encoding="utf-8")


def test_router_config_declares_qwen_and_deepseek_aliases():
    """Qwen/DeepSeek should expose aliases for explicit model selection."""
    assert "aliases: [\"qwen-2.5-coder-7b\"" in ROUTER_CONFIG_SOURCE
    assert "aliases: [\"deepseek-r1-7b\"" in ROUTER_CONFIG_SOURCE
    assert "aliases: [\"llama-3.3-8b-instruct\"" in ROUTER_CONFIG_SOURCE


def test_agent_router_supports_preferred_model_resolution():
    """Router should resolve external model identifiers and honor preferred model."""
    assert "self.model_aliases: Dict[str, str] = {}" in AGENT_ROUTER_SOURCE
    assert "def resolve_model_identifier" in AGENT_ROUTER_SOURCE
    assert "preferred_model: Optional[str] = None" in AGENT_ROUTER_SOURCE
    assert "resolved_model_id = self.resolve_model_identifier(preferred_model)" in AGENT_ROUTER_SOURCE
    assert "'explicit_model_used': explicit_model_used" in AGENT_ROUTER_SOURCE


def test_api_metrics_expose_per_model_latency_error_rate_and_tokens_per_second():
    """/metrics payload should include global and per-model health signals."""
    assert "def get_model_stats(self) -> Dict[str, Any]:" in API_SERVER_SOURCE
    assert '"error_rate_percent"' in API_SERVER_SOURCE
    assert '"tokens_per_second"' in API_SERVER_SOURCE
    assert '"per_model_metrics": metrics.get_model_stats()' in API_SERVER_SOURCE
    assert '"preferred_model": request.model' in API_SERVER_SOURCE

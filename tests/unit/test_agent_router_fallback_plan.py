# Needs: python-package:pytest>=9.0.2

from pathlib import Path


ROUTER_SOURCE = Path(__file__).resolve().parents[2] / "agent_router.py"
API_SOURCE = Path(__file__).resolve().parents[2] / "api_server.py"


def test_agent_router_exposes_routing_plan_method() -> None:
    content = ROUTER_SOURCE.read_text(encoding="utf-8")
    assert "def get_routing_plan(self, intent: Intent)" in content
    assert '"fallback_chain": self.get_fallback_chain(primary_model_id)' in content


def test_router_info_includes_routing_plans() -> None:
    content = API_SOURCE.read_text(encoding="utf-8")
    assert '"routing_plans": {' in content
    assert 'router.get_routing_plan(Intent.CODE)' in content

# Needs: python-package:pyyaml
# Needs: python-package:httpx
# Needs: python-package:prometheus-client

import importlib.util
from pathlib import Path

import pytest


_SPEC = importlib.util.spec_from_file_location("agent_router", Path(__file__).resolve().parents[2] / "agent_router.py")
agent_router = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
_SPEC.loader.exec_module(agent_router)
Intent = agent_router.Intent


@pytest.mark.asyncio
async def test_generate_updates_routed_metrics_and_fallback_rate(monkeypatch):
    router = agent_router.AgentRouter()

    for model in router.models.values():
        model.health_status = True

    async def fail_primary(**kwargs):
        if kwargs["model_id"] == "qwen-coder":
            return {"success": False, "error": "boom"}
        return {"success": True, "text": "ok", "model_id": kwargs["model_id"]}

    monkeypatch.setattr(router, "_try_model", fail_primary)
    monkeypatch.setattr(router, "classify_intent", lambda _: (Intent.CODE, 0.95))

    result = await router.generate(messages=[{"role": "user", "content": "write python code"}], prompt="test")

    assert result["success"] is True
    assert result["metadata"]["fallback_used"] is True

    fallback_rate = router.metrics.fallback_rate.labels(model="qwen-coder")._value.get()
    assert fallback_rate == 1.0

    routed_success = router.metrics.routed_requests.labels(
        model=result["metadata"]["model_id"],
        intent="code",
        fallback_used="true",
        status="success",
    )._value.get()
    assert routed_success == 1.0

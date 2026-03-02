# Needs: python-package:pytest>=9.0.2

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from internal_mcp_tool_policy import evaluate_tool_policy


@pytest.mark.unit
def test_policy_allows_call_when_allowlist_empty() -> None:
    decision = evaluate_tool_policy(tool_name="search_docs", allowed_tools_raw="")
    assert decision.allowed is True
    assert decision.reason is None


@pytest.mark.unit
def test_policy_allows_call_when_tool_is_allowlisted() -> None:
    decision = evaluate_tool_policy(
        tool_name="search_docs",
        allowed_tools_raw="search_docs, list_docs",
    )
    assert decision.allowed is True
    assert decision.reason is None


@pytest.mark.unit
def test_policy_denies_call_when_tool_is_not_allowlisted() -> None:
    decision = evaluate_tool_policy(
        tool_name="delete_docs",
        allowed_tools_raw="search_docs, list_docs",
    )
    assert decision.allowed is False
    assert "not allowed" in (decision.reason or "")


@pytest.mark.unit
def test_policy_denies_call_when_tool_name_missing() -> None:
    decision = evaluate_tool_policy(tool_name="", allowed_tools_raw="search_docs")
    assert decision.allowed is False
    assert decision.reason == "Missing required field: tool_name"


@pytest.mark.unit
def test_policy_allows_call_when_wildcard_present() -> None:
    decision = evaluate_tool_policy(
        tool_name="delete_docs",
        allowed_tools_raw="search_docs,*,list_docs",
    )
    assert decision.allowed is True
    assert decision.reason is None


@pytest.mark.unit
def test_policy_trims_allowlist_tokens_and_drops_empty_values() -> None:
    decision = evaluate_tool_policy(
        tool_name="search_docs",
        allowed_tools_raw="  , search_docs ,   ,list_docs  ",
    )
    assert decision.allowed is True
    assert decision.reason is None

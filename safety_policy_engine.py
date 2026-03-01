# Needs: python-package:pyyaml>=6.0.1
"""YAML-driven safety policy engine for request/response moderation."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

SUPPORTED_ACTIONS = {"allow", "block", "redact", "warn"}


@dataclass
class SafetyPolicyRule:
    id: str
    pattern: str
    action: str
    target: str = "both"
    replacement: str = "[REDACTED]"
    description: str = ""


@dataclass
class SafetyPolicyCategory:
    name: str
    enabled: bool = True
    default_action: str = "allow"
    rules: List[SafetyPolicyRule] = field(default_factory=list)


@dataclass
class PolicyMatch:
    category: str
    rule_id: str
    action: str
    matched_text: str
    description: str = ""


@dataclass
class SafetyPolicyResult:
    blocked: bool
    action: str
    content: str
    matches: List[PolicyMatch] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class SafetyPolicyEngine:
    """Apply YAML policy rules to request/response text payloads."""

    def __init__(self, categories: Dict[str, SafetyPolicyCategory]):
        self.categories = categories
        self._compiled_patterns: Dict[str, re.Pattern[str]] = {}
        for category in categories.values():
            for rule in category.rules:
                key = f"{category.name}:{rule.id}"
                self._compiled_patterns[key] = re.compile(rule.pattern, re.IGNORECASE)

    @classmethod
    def from_yaml(cls, config_path: str) -> "SafetyPolicyEngine":
        config_file = Path(config_path)
        if not config_file.exists():
            logger.warning("Safety policy config not found at %s. Using empty policy.", config_path)
            return cls(categories={})

        with config_file.open("r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle) or {}

        categories_payload = payload.get("categories", {})
        categories: Dict[str, SafetyPolicyCategory] = {}

        for name, category_config in categories_payload.items():
            default_action = str(category_config.get("action", "allow")).lower()
            if default_action not in SUPPORTED_ACTIONS:
                default_action = "allow"

            category = SafetyPolicyCategory(
                name=name,
                enabled=bool(category_config.get("enabled", True)),
                default_action=default_action,
            )

            for rule in category_config.get("rules", []):
                action = str(rule.get("action", category.default_action)).lower()
                if action not in SUPPORTED_ACTIONS:
                    logger.warning(
                        "Unknown action '%s' for rule '%s' in category '%s'; defaulting to allow",
                        action,
                        rule.get("id", "unknown"),
                        name,
                    )
                    action = "allow"

                category.rules.append(
                    SafetyPolicyRule(
                        id=str(rule.get("id", f"{name}-rule-{len(category.rules)}")),
                        pattern=str(rule.get("pattern", "")),
                        action=action,
                        target=str(rule.get("target", "both")).lower(),
                        replacement=str(rule.get("replacement", "[REDACTED]")),
                        description=str(rule.get("description", "")),
                    )
                )

            categories[name] = category

        return cls(categories=categories)

    def evaluate_text(self, content: str, target: str = "both") -> SafetyPolicyResult:
        """Evaluate text and return transformed content + policy outcomes."""
        if not content:
            return SafetyPolicyResult(blocked=False, action="allow", content=content)

        transformed = content
        matches: List[PolicyMatch] = []
        warnings: List[str] = []
        blocked = False
        dominant_action = "allow"

        for category in self.categories.values():
            if not category.enabled:
                continue

            for rule in category.rules:
                if rule.target not in ("both", target):
                    continue
                if not rule.pattern:
                    continue

                pattern_key = f"{category.name}:{rule.id}"
                compiled = self._compiled_patterns.get(pattern_key)
                if not compiled:
                    continue

                found = compiled.search(transformed)
                if not found:
                    continue

                matches.append(
                    PolicyMatch(
                        category=category.name,
                        rule_id=rule.id,
                        action=rule.action,
                        matched_text=found.group(0),
                        description=rule.description,
                    )
                )

                if rule.action == "block":
                    blocked = True
                    dominant_action = "block"
                elif rule.action == "redact" and dominant_action != "block":
                    transformed = compiled.sub(rule.replacement, transformed)
                    dominant_action = "redact"
                elif rule.action == "warn" and dominant_action not in ("block", "redact"):
                    dominant_action = "warn"
                    warnings.append(f"{category.name}:{rule.id}")

        return SafetyPolicyResult(
            blocked=blocked,
            action=dominant_action,
            content=transformed,
            matches=matches,
            warnings=warnings,
        )


def load_default_safety_policy_engine() -> SafetyPolicyEngine:
    """Load engine from SAFETY_POLICY_CONFIG or repository default path."""
    config_path = os.getenv("SAFETY_POLICY_CONFIG", "configs/safety-policy.yaml")
    return SafetyPolicyEngine.from_yaml(config_path)

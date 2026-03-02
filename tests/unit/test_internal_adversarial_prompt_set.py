import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPT_SET_PATH = REPO_ROOT / "tests" / "contract" / "fixtures" / "internal_adversarial_prompts.json"


REQUIRED_TECHNIQUES = {"camouflage", "role-play", "obfuscation"}
REQUIRED_CATEGORIES = {"jailbreak", "toxic", "exfiltration"}


def test_internal_prompt_set_has_required_coverage():
    suite = json.loads(PROMPT_SET_PATH.read_text(encoding="utf-8"))
    cases = suite["cases"]

    assert len(cases) >= 15

    categories = {case["category"] for case in cases}
    assert REQUIRED_CATEGORIES.issubset(categories)

    jailbreak_techniques = {
        case["technique"]
        for case in cases
        if case["category"] == "jailbreak"
    }
    assert REQUIRED_TECHNIQUES.issubset(jailbreak_techniques)


def test_internal_prompt_set_includes_brainego_specific_exfiltration_attempts():
    suite = json.loads(PROMPT_SET_PATH.read_text(encoding="utf-8"))
    cases = suite["cases"]

    brainego_exfiltration_prompts = [
        case
        for case in cases
        if case["category"] == "exfiltration"
        and "brainego" in case["prompt"].lower()
    ]

    assert len(brainego_exfiltration_prompts) >= 3

    for case in brainego_exfiltration_prompts:
        assert case["expected_behavior"] == "refuse_or_safe_redirect"

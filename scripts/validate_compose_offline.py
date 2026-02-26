#!/usr/bin/env python3
"""Offline Docker Compose structure validation for no-docker environments."""

from pathlib import Path


def _validate_with_pyyaml(raw_text: str) -> bool:
    """Validate using PyYAML when available."""
    try:
        import yaml  # type: ignore
    except ModuleNotFoundError:
        return False

    data = yaml.safe_load(raw_text)
    if not isinstance(data, dict):
        raise AssertionError("docker-compose.yaml must parse to a mapping")

    services = data.get("services")
    if not isinstance(services, dict):
        raise AssertionError("missing or invalid services section")

    required_services = ["api-server", "qdrant"]
    missing = [service for service in required_services if service not in services]
    if missing:
        raise AssertionError(f"missing service(s): {', '.join(missing)}")

    return True


def _validate_without_dependencies(raw_text: str) -> None:
    """Fallback validation without external Python dependencies."""
    required_snippets = [
        "services:",
        "  api-server:",
        "  qdrant:",
    ]

    for snippet in required_snippets:
        if snippet not in raw_text:
            raise AssertionError(f"missing expected compose structure: {snippet}")


def main() -> None:
    """Validate compose file existence and required services."""
    compose_path = Path("docker-compose.yaml")
    if not compose_path.exists():
        raise AssertionError("docker-compose.yaml missing")

    raw_text = compose_path.read_text()
    validated_with_yaml = _validate_with_pyyaml(raw_text)
    if not validated_with_yaml:
        _validate_without_dependencies(raw_text)

    print("compose_yaml_ok")


if __name__ == "__main__":
    main()

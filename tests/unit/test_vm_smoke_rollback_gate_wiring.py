"""Static wiring checks for VM post-deploy smoke + rollback gate."""

from pathlib import Path

SOURCE = Path("scripts/deploy/deploy_vm.sh").read_text(encoding="utf-8")


def test_vm_deploy_runs_smoke_tests_and_attempts_auto_rollback() -> None:
    assert "run_smoke_tests" in SOURCE
    assert "perform_smoke_rollback" in SOURCE
    assert "smoke_tests_failed" in SOURCE


def test_vm_deploy_emits_skip_smoke_audit_trail() -> None:
    assert "SKIP_SMOKE_LOG" in SOURCE
    assert "log_skip_smoke" in SOURCE

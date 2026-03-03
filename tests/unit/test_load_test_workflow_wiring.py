"""Static checks for k6 merge + nightly workflow wiring."""

from pathlib import Path

SOURCE = Path('.github/workflows/load-test.yml').read_text(encoding='utf-8')


def test_workflow_runs_on_pr_push_and_schedule() -> None:
    assert 'pull_request:' in SOURCE
    assert 'schedule:' in SOURCE
    assert 'cron: "0 2 * * *"' in SOURCE


def test_workflow_has_nightly_job_and_merge_suite_script() -> None:
    assert 'nightly-load-test:' in SOURCE
    assert './scripts/load_test/run_k6_nightly_suite.sh' in SOURCE
    assert './scripts/load_test/run_k6_suite.sh' in SOURCE


def test_workflow_wires_force_run_into_merge_job() -> None:
    assert "K6_FORCE_RUN: ${{ github.event.inputs.force_run || 'false' }}" in SOURCE
    assert "K6_ABORT_ON_HEALTHCHECK_FAILURE: 'true'" in SOURCE

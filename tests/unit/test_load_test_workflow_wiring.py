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

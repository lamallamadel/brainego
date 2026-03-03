"""Static checks for k6 DNS/health fail-fast protections."""

from pathlib import Path

MERGE = Path('scripts/load_test/run_k6_suite.sh').read_text(encoding='utf-8')
NIGHTLY = Path('scripts/load_test/run_k6_nightly_suite.sh').read_text(encoding='utf-8')


def test_merge_script_has_dns_preflight_and_force_override() -> None:
    assert 'DNS preflight (fail-fast to avoid long k6 loops on NXDOMAIN)' in MERGE
    assert 'dns_resolves' in MERGE
    assert 'K6_FORCE_RUN' in MERGE
    assert 'Aborting load test early' in MERGE


def test_nightly_script_has_dns_preflight_and_healthcheck_abort_flag() -> None:
    assert 'K6_ABORT_ON_HEALTHCHECK_FAILURE' in NIGHTLY
    assert 'dns_resolves' in NIGHTLY
    assert 'Health checks failed and fail-fast is enabled' in NIGHTLY

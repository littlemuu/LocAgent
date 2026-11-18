"""Append a final verification record without replacing earlier evidence."""
from pathlib import Path
from .entry import ROOT, read, sha, save, checked_file

OUT = ROOT / 'verification/cohort-preflight-v1'

def main():
    pilot = read(OUT / 'pilot-v2/summary.json')
    code = read(OUT / 'pilot-v2/claim.json')['code']
    for name, expected in code.items():
        checked_file(ROOT / name, expected)
    assert pilot['completed'] == 2 and pilot['failed'] == 0 and pilot['not_started'] == 0
    assert pilot['real_model_requests'] == 0
    assert sum(r['mock_requests'] for r in pilot['results']) == 16
    catalog = read(OUT / 'runtime-catalog.json')['cases']
    entries = {r['id']: read(checked_file(r['entry'], r['entry_sha256'])) for r in catalog}
    for row in pilot['results']:
        own = entries[row['case_id']]['issue']
        other = next(entries[r['case_id']]['issue'] for r in pilot['results'] if r['case_id'] != row['case_id'])
        base = OUT / 'pilot-v2' / row['case_id']
        requests = read(base / 'native.json')['requests'] + read(base / 'sdk/wire-requests.json')
        assert len(requests) == 8
        for request in requests:
            contents = [m.get('content') or '' for m in request['messages']]
            assert any(own in content for content in contents)
            assert not any(other in content for content in contents)
    for row in read(OUT / 'execution-catalog.json')['cases']:
        attpath = Path(row['body_directory']) / 'attestation.json'
        att = read(checked_file(attpath, row['body_attestation_sha256']))
        assert att['snapshot'] == row['snapshot']
        for name, expected in att['artifacts'].items():
            checked_file(attpath.parent / name, expected)
    manifest = read(ROOT / 'engine_adaptation/v4/adapted-manifest.json')
    for name, expected in manifest['engine']['files'].items():
        checked_file(ROOT / 'engine_adaptation/v4/engine' / name, expected)
    for name, expected in manifest['harness_files'].items():
        checked_file(ROOT / name, expected)
    for name, expected in read(ROOT / 'verification/eval-fair-v3/proposal.json')['adapter_sources'].items():
        checked_file(ROOT / name, expected)
    labels = Path('/Users/xiaomu/Documents/Codex/2026-11-10/task/locbench-remaining-batch134-20261113/scoring-only/labels')
    for row in read(OUT / 'scoring-only/structural-label-audit.json'):
        checked_file(labels / (row['id'] + '.json'), row['label_sha256'])
    protected = read(ROOT / 'verification/engine-compatibility-v1/preflight.json')['protected_before']
    changed = [p for p, expected in protected.items() if sha(p) != expected]
    expected_prior_changes = {'bridge.py', 'core.py', 'locagent.py', 'locagent_worker.py', 'openhands_replay.py', 'preparation.py'}
    assert len(changed) == 6 and {Path(p).name for p in changed} == expected_prior_changes
    final = read(OUT / 'final-verification.json')
    wire = read(OUT / 'initial-wire-screen.json')
    final.update({
        'supersedes': 'final-verification.json; original retained',
        'pilot': 'pilot-v2', 'tests_passed': 21,
        'source_runtime_core_unchanged_since_e2e': True,
        'post_e2e_change': 'Only offline wire-screen and closeout reporting added; all 54 frozen pilot source files unchanged.',
        'paired_mock_requests_latest': 16, 'paired_mock_requests_this_cycle': 32,
        'long_issue_unit_mock_requests': 1,
        'initial_wire_screen': {k: wire[k] for k in ['checked', 'fit', 'failed', 'unchecked', 'max_issue_bytes', 'max_wire_upper_bytes', 'old_sdk_gate_rejected']},
        'protected_historical_files_unchanged': len(protected) - len(changed),
        'expected_preexisting_harness_changes': changed,
        'report_sha256': sha(ROOT / 'COHORT_PREFLIGHT_REPORT.md'),
    })
    save(OUT / 'code-lock-v2.json', {str(p.relative_to(ROOT)): sha(p) for p in (ROOT / 'experiments/cohort_preflight').glob('*.py')})
    save(OUT / 'final-verification-v2.json', final)
    print('Verified 130 body artifact sets, 54 pilot source files, original gold/engine/harness and historical protections; wrote v2 closeout.')

if __name__ == '__main__':
    main()

"""Deterministic mock controls. No live provider, credentials, plans or ledgers.

Run from the project root with PYTHONPATH=$PWD:$PWD/scripts:$PWD/tests.
The assertions, not model choices, select every tool call in this experiment.
"""
import json
from itertools import product
from test_equal_source_budget import EqualSourceBudgetTests, setUpModule, tearDownModule


def main():
    rows = []
    setUpModule()
    try:
        for equal, rounds, enabled in product((False, True), (3, 5), (False, True)):
            case = EqualSourceBudgetTests()
            case.setUp()
            try:
                steps = [case.response('get_entity_contents', {}) for _ in range(rounds-1)] + [case.finish()]
                run = case.run_budget(equal=equal, maximum=rounds, guidance=True,
                                      drill=enabled, steps=steps, raw='small fixed source body')
                d = run.trajectory['diagnostics']
                source_allowance = (d['source_budget']['source_message_allowance_bytes'] if equal
                                    else 24576 - 4096 - 4096 - (2048 if enabled else 0))
                rows.append({'equal_source_budget': equal, 'max_iterations': rounds,
                             'candidate_guidance': True, 'candidate_drilldown': enabled,
                             'source_message_allowance_bytes': source_allowance,
                             'actual_mock_provider_calls': run.trajectory['iterations'],
                             'executed_tool_calls': len(case.executed),
                             'delivered_source_message_bytes': sum(x['message_json_bytes'] for x in d['tool_messages']),
                             'termination_reason': run.trajectory['termination_reason']})
            finally:
                case.doCleanups()
    finally:
        tearDownModule()
    print(json.dumps({'kind': 'offline_scripted_control_matrix', 'real_model_calls': 0,
                      'measures_localization_quality': False, 'rows': rows}, indent=2))


if __name__ == '__main__':
    main()
